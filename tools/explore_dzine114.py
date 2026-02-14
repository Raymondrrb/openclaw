"""Phase 114: Fix Ray character selection + generate image + robust upload test.
P113 issues:
- Ray click returned false — character list items not found by text search
- file_chooser timeout on both Assets upload and sidebar Upload
- Character Sheet and 360° Video mapped successfully

Goal: 1) Debug character list visibility and find Ray
      2) Select Ray and generate an image
      3) Find Upload mechanism (maybe drag-and-drop or hidden input)
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


def wait_for_canvas(page, max_wait=40):
    for i in range(max_wait):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    return False


def cleanup_tabs(ctx):
    pages = ctx.pages
    print(f"  Found {len(pages)} open tabs", flush=True)
    kept = False
    for p in pages:
        url = p.url or ""
        if "dzine.ai" in url:
            if kept:
                try:
                    p.close()
                except Exception:
                    pass
            else:
                kept = True
        elif url in ("", "about:blank", "chrome://newtab/"):
            try:
                p.close()
            except Exception:
                pass
    print(f"  Tabs after cleanup: {len(ctx.pages)}", flush=True)


def close_all_panels(page):
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
    }""")
    page.wait_for_timeout(1000)


def open_sidebar_tool(page, target_y):
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, target_y)
    page.wait_for_timeout(2500)
    close_dialogs(page)


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    cleanup_tabs(ctx)

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  STEP 1: Open Character > Generate Images
    # ============================================================
    print("\n=== STEP 1: Open Character > Generate Images ===", flush=True)

    open_sidebar_tool(page, 306)

    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="collapse-option"], button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Generate Images') && r.width > 100 && r.x < 350) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ============================================================
    #  STEP 2: Click "Choose a Character" and MAP the dropdown
    # ============================================================
    print("\n=== STEP 2: Map character dropdown ===", flush=True)

    # Click "Choose a Character"
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, [class*="choose"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Choose a Character') && r.width > 100) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Screenshot first to see state
    ss(page, "P114_01_character_dropdown")

    # Map ALL visible character list items
    char_list = page.evaluate("""() => {
        var items = [];

        // Strategy 1: Find .c-character-list items
        var list = document.querySelector('.c-character-list');
        if (list) {
            for (var item of list.querySelectorAll('.item, button, [class*="character"]')) {
                var r = item.getBoundingClientRect();
                if (r.width < 30 || r.height < 15) continue;
                var text = (item.innerText || '').trim();
                items.push({
                    strategy: 'c-character-list',
                    tag: item.tagName,
                    class: (item.className || '').toString().substring(0, 60),
                    text: text.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    clickX: Math.round(r.x + r.width/2),
                    clickY: Math.round(r.y + r.height/2),
                });
            }
        }

        // Strategy 2: Search for any element with "Ray" text
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Ray' && r.width > 20 && r.width < 300 && r.height > 10 && r.height < 60) {
                items.push({
                    strategy: 'text-search-Ray',
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    text: 'Ray',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    clickX: Math.round(r.x + r.width/2),
                    clickY: Math.round(r.y + r.height/2),
                });
            }
        }

        // Strategy 3: Find items that contain "Ray" (broader)
        for (var el of document.querySelectorAll('.item, [class*="character-item"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Ray') && r.width > 50) {
                items.push({
                    strategy: 'item-contains-Ray',
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    text: text.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    clickX: Math.round(r.x + r.width/2),
                    clickY: Math.round(r.y + r.height/2),
                });
            }
        }

        // Strategy 4: Check if character list is visible
        var listInfo = null;
        if (list) {
            var r = list.getBoundingClientRect();
            listInfo = {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                visible: r.width > 0 && r.height > 0,
                childCount: list.children.length,
                text: (list.innerText || '').substring(0, 200),
            };
        }

        return {items: items, listInfo: listInfo};
    }""")

    print(f"  Character list info: {json.dumps(char_list.get('listInfo'))}", flush=True)
    print(f"\n  Character items ({len(char_list.get('items', []))}):", flush=True)
    for item in char_list.get('items', []):
        print(f"    [{item['strategy']}] <{item['tag']}> .{item['class'][:40]} '{item['text']}' ({item['x']},{item['y']}) {item['w']}x{item['h']}", flush=True)

    # ============================================================
    #  STEP 3: Click Ray
    # ============================================================
    print("\n=== STEP 3: Click Ray ===", flush=True)

    # Find Ray item and click it
    ray_items = [i for i in char_list.get('items', []) if 'Ray' in i.get('text', '')]

    if ray_items:
        # Prefer the button/item with the right strategy
        ray = ray_items[0]
        for r in ray_items:
            if r['strategy'] == 'c-character-list':
                ray = r
                break

        print(f"  Clicking Ray at ({ray['clickX']},{ray['clickY']})", flush=True)
        page.mouse.click(ray['clickX'], ray['clickY'])
        page.wait_for_timeout(2000)
    else:
        # Fall back: try using P112 coordinates directly
        print("  Ray not found in items. Trying P112 coordinates (492, 445)...", flush=True)
        # P112 showed Ray at button (372, 425) 240x40 → center = (492, 445)
        page.mouse.click(492, 445)
        page.wait_for_timeout(2000)

    ss(page, "P114_02_ray_clicked")

    # Check if Ray is selected
    selected = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        // Check if "Choose a Character" changed
        var hasChoose = false;
        for (var el of panel.querySelectorAll('*')) {
            if ((el.innerText || '').includes('Choose a Character')) {
                var r = el.getBoundingClientRect();
                if (r.width > 80 && r.x < 300) { hasChoose = true; break; }
            }
        }

        // Check for character avatar/name displayed
        var charName = null;
        for (var el of panel.querySelectorAll('[class*="selected"], [class*="char-name"], [class*="avatar"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.length > 0 && r.x < 300 && r.width > 20) {
                charName = text.substring(0, 30);
                break;
            }
        }

        // Check for character thumbnail
        var hasThumb = false;
        for (var img of panel.querySelectorAll('img')) {
            var r = img.getBoundingClientRect();
            if (r.width > 30 && r.width < 100 && r.x < 200 && r.y < 120) {
                hasThumb = true;
                break;
            }
        }

        // Generate button state
        var gen = panel.querySelector('.generative');
        var genDisabled = gen ? gen.disabled : true;
        var genText = gen ? (gen.innerText || '').trim() : '';

        // Warning
        var fullText = (panel.innerText || '');
        var warning = null;
        if (fullText.includes('Please choose')) warning = 'choose character';
        if (fullText.includes('Please enter')) warning = 'enter prompt';

        return {
            hasChoose: hasChoose,
            charName: charName,
            hasThumb: hasThumb,
            genDisabled: genDisabled,
            genText: genText,
            warning: warning,
            panelText: fullText.substring(0, 200),
        };
    }""")
    print(f"  Selected: {json.dumps(selected, indent=2)}", flush=True)

    if selected.get('warning') == 'choose character':
        print("  Ray still not selected. Trying to scroll character list...", flush=True)

        # Maybe the character list needs scrolling
        scrolled = page.evaluate("""() => {
            var list = document.querySelector('.c-character-list');
            if (!list) return 'no list';
            // Scroll to bottom
            list.scrollTop = list.scrollHeight;
            return 'scrolled to ' + list.scrollHeight;
        }""")
        print(f"  {scrolled}", flush=True)
        page.wait_for_timeout(1000)

        # Search again after scroll
        ray2 = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Ray' && r.width > 20 && r.width < 300 && r.height > 10 && r.height < 60 && r.y > 0) {
                    items.push({
                        tag: el.tagName,
                        class: (el.className || '').toString().substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        parent: el.parentElement ? (el.parentElement.className || '').toString().substring(0, 40) : '',
                    });
                }
            }
            return items;
        }""")
        print(f"  Ray elements after scroll: {json.dumps(ray2)}", flush=True)

        if ray2:
            r = ray2[0]
            # Click the element or its parent
            page.mouse.click(r['x'] + r['w'] // 2, r['y'] + r['h'] // 2)
            page.wait_for_timeout(2000)
            ss(page, "P114_02b_ray_retry")

    # ============================================================
    #  STEP 4: Type prompt and generate
    # ============================================================
    print("\n=== STEP 4: Type prompt + generate ===", flush=True)

    # Re-check generate state
    gen_state = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var gen = panel.querySelector('.generative');
        if (!gen) return null;
        var r = gen.getBoundingClientRect();
        return {
            text: (gen.innerText || '').trim(),
            disabled: gen.disabled,
            x: Math.round(r.x + r.width/2),
            y: Math.round(r.y + r.height/2),
        };
    }""")
    print(f"  Generate state: {json.dumps(gen_state)}", flush=True)

    if gen_state and gen_state.get('disabled'):
        # Still disabled — check full panel state
        full_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            return panel ? (panel.innerText || '').substring(0, 400) : 'no panel';
        }""")
        print(f"  Full state: {full_state[:200]}", flush=True)

    # Type prompt regardless
    prompt_text = "YouTube presenter holding premium wireless headphones, studio background, confident pose, professional lighting"

    ta = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var ta = panel.querySelector('.custom-textarea, textarea, .prompt-textarea');
        if (ta) {
            var r = ta.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }
        return null;
    }""")

    if ta:
        page.mouse.click(ta['x'], ta['y'])
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(prompt_text, delay=10)
        page.wait_for_timeout(1000)
        print(f"  Typed prompt ({len(prompt_text)} chars)", flush=True)

    # Re-check and try to generate
    gen_state2 = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var gen = panel.querySelector('.generative');
        if (!gen) return null;
        var r = gen.getBoundingClientRect();
        return {
            text: (gen.innerText || '').trim(),
            disabled: gen.disabled,
            x: Math.round(r.x + r.width/2),
            y: Math.round(r.y + r.height/2),
        };
    }""")
    print(f"  Generate state after prompt: {json.dumps(gen_state2)}", flush=True)

    ss(page, "P114_03_ready_to_generate")

    if gen_state2 and not gen_state2.get('disabled'):
        initial_results = page.evaluate("() => document.querySelectorAll('.result-item').length")
        print(f"  Generating... ({gen_state2['text']})", flush=True)
        page.mouse.click(gen_state2['x'], gen_state2['y'])

        # Wait for generation
        for i in range(40):
            elapsed = (i + 1) * 3
            check = page.evaluate("""(initCount) => {
                var results = document.querySelectorAll('.result-item');
                var newCount = results.length;
                var newest = results[0];
                var newestText = newest ? (newest.innerText || '').trim().substring(0, 80) : '';
                var newestImg = newest ? newest.querySelector('img') : null;
                var imgLoaded = newestImg ? newestImg.naturalWidth > 0 : false;
                var progress = null;
                for (var el of document.querySelectorAll('.result-item')) {
                    var m = (el.innerText || '').match(/(\\d+)%/);
                    if (m) { progress = m[1] + '%'; break; }
                }
                return {
                    newResults: newCount - initCount,
                    imgLoaded: imgLoaded,
                    progress: progress,
                    newestText: newestText.substring(0, 60),
                };
            }""", initial_results)

            if check.get('newResults', 0) > 0 and check.get('imgLoaded'):
                print(f"  Result with image at {elapsed}s!", flush=True)
                break
            if check.get('progress') and i % 3 == 0:
                print(f"  ...{elapsed}s {check['progress']}", flush=True)
            elif i % 5 == 0:
                print(f"  ...{elapsed}s waiting", flush=True)

            page.wait_for_timeout(3000)

        ss(page, "P114_04_generation_result")

        # Check the result
        result_info = page.evaluate("""() => {
            var first = document.querySelector('.result-item');
            if (!first) return null;
            var text = (first.innerText || '').substring(0, 120);
            var imgs = [];
            for (var img of first.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.width > 30) {
                    imgs.push({
                        src: (img.src || '').substring(0, 120),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            return {text: text, images: imgs.slice(0, 4)};
        }""")
        print(f"  Result: {json.dumps(result_info, indent=2)}", flush=True)

    # ============================================================
    #  STEP 5: Upload deep investigation
    # ============================================================
    print("\n=== STEP 5: Upload investigation ===", flush=True)

    # Check ALL input[type=file] on the page (including hidden ones)
    all_file_inputs = page.evaluate("""() => {
        var inputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            var r = inp.getBoundingClientRect();
            inputs.push({
                accept: inp.accept || '*',
                multiple: inp.multiple,
                id: inp.id || '',
                name: inp.name || '',
                class: (inp.className || '').toString(),
                hidden: inp.hidden || r.width === 0,
                display: window.getComputedStyle(inp).display,
                parent: (inp.parentElement?.tagName || '') + '.' + (inp.parentElement?.className || '').toString().substring(0, 30),
            });
        }
        return inputs;
    }""")
    print(f"  All file inputs on page ({len(all_file_inputs)}):", flush=True)
    for fi in all_file_inputs:
        print(f"    accept='{fi['accept']}' hidden={fi['hidden']} display={fi['display']}", flush=True)
        print(f"      parent: {fi['parent']}", flush=True)

    # If file inputs found, test clicking them
    if all_file_inputs:
        # Click the first one via JS
        print("\n  Triggering hidden file input via JS...", flush=True)
        try:
            with page.expect_file_chooser(timeout=3000) as fc_info:
                page.evaluate("() => { var inp = document.querySelector('input[type=\"file\"]'); if (inp) inp.click(); }")
            fc = fc_info.value
            print(f"  FILE CHOOSER from hidden input!", flush=True)
            print(f"    Multiple: {fc.is_multiple}", flush=True)
            # Don't actually select files, just cancel
            page.keyboard.press("Escape")
        except Exception as e:
            print(f"  No file chooser: {e}", flush=True)

    # Try the canvas area for drag-and-drop support
    print("\n  Checking drag-and-drop support...", flush=True)
    dnd = page.evaluate("""() => {
        // Check if canvas has drop event listeners
        var canvas = document.querySelector('#canvas') || document.querySelector('.lower-canvas');
        if (!canvas) return {error: 'no canvas'};

        // Check for drag-drop container
        var dropContainers = [];
        for (var el of document.querySelectorAll('[class*="drop"], [class*="drag-drop"]')) {
            var r = el.getBoundingClientRect();
            dropContainers.push({
                class: (el.className || '').toString().substring(0, 60),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Check for paste event handlers (Ctrl+V image paste)
        var hasPaste = false;
        try {
            var events = getEventListeners(document);
            hasPaste = !!events.paste;
        } catch(e) {}

        return {dropContainers: dropContainers, hasPaste: hasPaste};
    }""")
    print(f"  Drop containers: {json.dumps(dnd.get('dropContainers', []))}", flush=True)

    # Check the "Describe the desired image" input at bottom of canvas
    bottom_input = page.evaluate("""() => {
        var bottom = document.querySelector('[class*="describe"], [class*="bottom-input"], [class*="canvas-prompt"]');
        if (!bottom) {
            // Search by position — bottom center area
            for (var el of document.querySelectorAll('input, [contenteditable], [class*="prompt"]')) {
                var r = el.getBoundingClientRect();
                if (r.y > 800 && r.x > 300 && r.x < 600 && r.width > 100) {
                    return {
                        tag: el.tagName,
                        class: (el.className || '').toString().substring(0, 60),
                        placeholder: el.getAttribute('placeholder') || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                }
            }
        }
        return null;
    }""")
    print(f"  Bottom canvas input: {json.dumps(bottom_input)}", flush=True)

    # Check the upload button that was found at (404, 888) in P112
    upload_at_bottom = page.evaluate("""() => {
        var btn = document.querySelector('.upload-image-btn');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {
            class: (btn.className || '').toString().substring(0, 60),
            text: (btn.innerText || '').trim(),
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            title: btn.title || '',
        };
    }""")
    print(f"  Bottom upload btn: {json.dumps(upload_at_bottom)}", flush=True)

    if upload_at_bottom:
        print("  Trying file_chooser on bottom upload button...", flush=True)
        try:
            with page.expect_file_chooser(timeout=3000) as fc_info:
                page.mouse.click(upload_at_bottom['x'] + upload_at_bottom['w'] // 2,
                                upload_at_bottom['y'] + upload_at_bottom['h'] // 2)
            fc = fc_info.value
            print(f"  FILE CHOOSER from bottom upload!", flush=True)
            print(f"    Multiple: {fc.is_multiple}", flush=True)
            page.keyboard.press("Escape")
        except Exception as e:
            print(f"  No file chooser: {e}", flush=True)

    ss(page, "P114_05_upload_investigation")

    # Final credits
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 1000 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\n  Credits: {credits}", flush=True)

    print(f"\n\n===== PHASE 114 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
