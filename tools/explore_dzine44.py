"""Phase 44: Target the exact button.upload in pick-panel for file chooser.

From P43: dialog is div.pick-panel at (440,197) 560x506.
Upload zone is <button class="upload"> Drop or select images here </button>.
Canvas thumbnails are <button class="image-item"> at (464,403) 96x96.
No iframes, no shadow DOM. Vue.js app (data-v-b3d4a4ae).
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

TEST_IMAGE = SS_DIR / "e2e31_thumbnail.png"


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


def open_cc_reference_pick(page):
    """Open CC panel → Reference → Pick Image dialog. Returns True if dialog opened."""
    print("\n  Opening CC → Reference → Pick Image...", flush=True)

    # Click Txt2Img first to ensure panel toggle works
    page.mouse.click(40, 197)
    page.wait_for_timeout(1000)
    # Click Character
    page.mouse.click(40, 306)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Click Generate Images if needed
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Generate Images')) { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    # Select Ray character
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('button')) {
            if ((el.innerText || '').trim() === 'Ray') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    # Click Reference button (find visible one)
    ref_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            var classes = (btn.className || '').toString();
            if (text === 'Reference' && r.width > 30 && r.x > 50 && r.x < 350 && r.y > 400) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y), classes: classes.substring(0, 40)};
            }
        }
        return null;
    }""")
    print(f"  Reference clicked: {ref_clicked}", flush=True)
    page.wait_for_timeout(2000)

    # Click Pick Image button
    pick_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.width > 50 && r.x > 50 && r.x < 350) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
        }
        return null;
    }""")
    print(f"  Pick Image clicked: {pick_clicked}", flush=True)
    page.wait_for_timeout(2000)

    # Verify dialog opened
    dialog = page.evaluate("""() => {
        var el = document.querySelector('.pick-panel');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    }""")
    print(f"  Dialog: {dialog}", flush=True)
    return dialog is not None


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

    if not open_cc_reference_pick(page):
        print("  FAILED to open dialog!", flush=True)
        ss(page, "P44_00_failed")
        sys.stdout.flush()
        os._exit(1)

    ss(page, "P44_01_dialog_open")

    # ============================================================
    #  STRATEGY 1: Find button.upload and get EXACT position
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STRATEGY 1: button.upload with expect_file_chooser", flush=True)
    print("=" * 60, flush=True)

    upload_btn = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        if (!panel) return null;
        var btn = panel.querySelector('button.upload');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {
            tag: btn.tagName,
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            text: (btn.innerText || '').trim(),
            cursor: window.getComputedStyle(btn).cursor,
            classes: (btn.className || '').toString(),
            display: window.getComputedStyle(btn).display,
            visibility: window.getComputedStyle(btn).visibility,
            opacity: window.getComputedStyle(btn).opacity,
        };
    }""")
    print(f"  Upload button: {upload_btn}", flush=True)

    if upload_btn:
        cx = upload_btn['x'] + upload_btn['w'] // 2
        cy = upload_btn['y'] + upload_btn['h'] // 2
        print(f"  Center: ({cx}, {cy})", flush=True)

        # Approach 1a: Click the exact button with expect_file_chooser
        print("\n  1a: Mouse click at button center + expect_file_chooser...", flush=True)
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)
            fc = fc_info.value
            print(f"  *** FILE CHOOSER! *** Multiple={fc.is_multiple}", flush=True)
            if TEST_IMAGE.exists():
                fc.set_files(str(TEST_IMAGE))
                page.wait_for_timeout(5000)
                ss(page, "P44_02_uploaded_1a")
                print("  *** FILE UPLOADED VIA 1a! ***", flush=True)
        except Exception as e:
            print(f"  1a failed: {e}", flush=True)

            # Approach 1b: Use Playwright locator click
            print("\n  1b: Playwright locator click...", flush=True)
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.locator('.pick-panel button.upload').click()
                fc = fc_info.value
                print(f"  *** FILE CHOOSER via locator! *** Multiple={fc.is_multiple}", flush=True)
                if TEST_IMAGE.exists():
                    fc.set_files(str(TEST_IMAGE))
                    page.wait_for_timeout(5000)
                    ss(page, "P44_02_uploaded_1b")
                    print("  *** FILE UPLOADED VIA 1b! ***", flush=True)
            except Exception as e2:
                print(f"  1b failed: {e2}", flush=True)

                # Approach 1c: JS click + expect_file_chooser
                print("\n  1c: JS click + expect_file_chooser...", flush=True)
                try:
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        page.evaluate("""() => {
                            var btn = document.querySelector('.pick-panel button.upload');
                            if (btn) btn.click();
                        }""")
                    fc = fc_info.value
                    print(f"  *** FILE CHOOSER via JS click! ***", flush=True)
                    if TEST_IMAGE.exists():
                        fc.set_files(str(TEST_IMAGE))
                        page.wait_for_timeout(5000)
                        ss(page, "P44_02_uploaded_1c")
                        print("  *** FILE UPLOADED VIA 1c! ***", flush=True)
                except Exception as e3:
                    print(f"  1c failed: {e3}", flush=True)

    # ============================================================
    #  STRATEGY 2: Intercept at CDP level — listen for file chooser
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STRATEGY 2: CDP-level file chooser intercept", flush=True)
    print("=" * 60, flush=True)

    # Check if there's a hidden input[type=file] anywhere that gets programmatically clicked
    hidden_inputs = page.evaluate("""() => {
        var items = [];
        for (const inp of document.querySelectorAll('input')) {
            var r = inp.getBoundingClientRect();
            items.push({
                type: inp.type,
                accept: inp.accept || '',
                display: window.getComputedStyle(inp).display,
                visibility: window.getComputedStyle(inp).visibility,
                w: Math.round(r.width), h: Math.round(r.height),
                parent: inp.parentElement ? inp.parentElement.className : '',
            });
        }
        return items;
    }""")
    print(f"  All inputs ({len(hidden_inputs)}):", flush=True)
    for inp in hidden_inputs[:10]:
        print(f"    type={inp['type']} accept='{inp['accept']}' display={inp['display']} vis={inp['visibility']} {inp['w']}x{inp['h']} parent='{inp['parent'][:30]}'", flush=True)

    # Approach 2a: Inject a file input, link it to the upload button handler
    print("\n  2a: Inject file input and trigger via Vue's event system...", flush=True)
    inject_result = page.evaluate("""() => {
        // Find the upload button's Vue component
        var btn = document.querySelector('.pick-panel button.upload');
        if (!btn) return {error: 'button not found'};

        // Check for Vue instance
        var vueKeys = Object.keys(btn).filter(function(k) { return k.startsWith('__vue'); });

        // Check for event listeners via getEventListeners (Chrome DevTools only)
        var listeners = [];
        try {
            var el = btn;
            // Walk the Vue component tree
            for (var key of vueKeys) {
                var vue = btn[key];
                listeners.push({key: key, type: typeof vue, keys: Object.keys(vue || {}).slice(0, 10)});
            }
        } catch(e) {
            listeners.push({error: e.message});
        }

        // Check for data-v attributes
        var dataV = [];
        for (var attr of btn.attributes) {
            if (attr.name.startsWith('data-v')) {
                dataV.push(attr.name);
            }
        }

        return {
            vueKeys: vueKeys,
            dataV: dataV,
            listeners: listeners,
            parentTag: btn.parentElement.tagName,
            parentClasses: (btn.parentElement.className || '').toString(),
        };
    }""")
    print(f"  Vue inspection: {json.dumps(inject_result, indent=2)}", flush=True)

    # ============================================================
    #  STRATEGY 3: Create our own file input and dispatch
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STRATEGY 3: Create hidden file input + dispatch change event", flush=True)
    print("=" * 60, flush=True)

    # This approach creates a file input, uses set_input_files, then
    # dispatches the change event to the upload button's parent
    print("  3a: Creating hidden file input...", flush=True)
    page.evaluate("""() => {
        var input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.id = '__test_file_input';
        input.style.cssText = 'position:fixed;top:-100px;left:-100px;opacity:0;';
        document.body.appendChild(input);
    }""")

    try:
        page.locator('#__test_file_input').set_input_files(str(TEST_IMAGE))
        print("  File set on injected input!", flush=True)

        # Now try to trigger the Vue component's upload handler
        dispatch_result = page.evaluate("""() => {
            var fileInput = document.getElementById('__test_file_input');
            if (!fileInput || !fileInput.files || fileInput.files.length === 0) return {error: 'no files'};

            var file = fileInput.files[0];

            // Try to find the upload handler in Vue
            var btn = document.querySelector('.pick-panel button.upload');
            if (!btn) return {error: 'no upload button'};

            // Strategy: dispatch a drop event with the file on the upload button
            var dt = new DataTransfer();
            dt.items.add(file);

            var dropEvent = new DragEvent('drop', {
                bubbles: true,
                cancelable: true,
                dataTransfer: dt,
            });
            btn.dispatchEvent(dropEvent);

            // Also try on the pick-types container
            var pickTypes = document.querySelector('.pick-panel .pick-types');
            if (pickTypes) {
                var dropEvent2 = new DragEvent('drop', {
                    bubbles: true,
                    cancelable: true,
                    dataTransfer: dt,
                });
                pickTypes.dispatchEvent(dropEvent2);
            }

            // Also try change event on a cloned input
            var changeEvent = new Event('change', {bubbles: true});
            fileInput.dispatchEvent(changeEvent);

            return {
                fileName: file.name,
                fileSize: file.size,
                fileType: file.type,
                dispatched: ['drop on button', 'drop on pick-types', 'change on input'],
            };
        }""")
        print(f"  Dispatch result: {json.dumps(dispatch_result, indent=2)}", flush=True)

        page.wait_for_timeout(3000)
        ss(page, "P44_03_after_drop")

        # Check if anything changed
        after_state = page.evaluate("""() => {
            var panel = document.querySelector('.pick-panel');
            if (!panel) return {dialogGone: true};
            return {
                dialogGone: false,
                html: panel.innerHTML.substring(0, 500),
            };
        }""")
        print(f"  After state: dialog gone={after_state.get('dialogGone', 'unknown')}", flush=True)
        if not after_state.get('dialogGone'):
            print(f"  HTML preview: {after_state.get('html', '')[:200]}", flush=True)

    except Exception as e:
        print(f"  3a failed: {e}", flush=True)

    # ============================================================
    #  STRATEGY 4: Click canvas thumbnail (image-item)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STRATEGY 4: Click canvas image-item thumbnail", flush=True)
    print("=" * 60, flush=True)

    # First check if dialog is still open
    dialog_open = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        if (!panel) return false;
        var r = panel.getBoundingClientRect();
        return r.width > 100;
    }""")

    if not dialog_open:
        print("  Dialog closed! Reopening...", flush=True)
        open_cc_reference_pick(page)
        page.wait_for_timeout(2000)

    # Find all image-item buttons in pick-panel
    image_items = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        if (!panel) return [];
        var items = [];
        for (const btn of panel.querySelectorAll('button.image-item')) {
            var r = btn.getBoundingClientRect();
            var style = btn.getAttribute('style') || '';
            items.push({
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                style: style.substring(0, 100),
                hasBgImage: style.includes('background'),
            });
        }
        return items;
    }""")
    print(f"  Image items in dialog ({len(image_items)}):", flush=True)
    for item in image_items:
        print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} bgImg={item['hasBgImage']} style='{item['style'][:60]}'", flush=True)

    if image_items:
        item = image_items[0]
        cx = item['x'] + item['w'] // 2
        cy = item['y'] + item['h'] // 2
        print(f"\n  Clicking first image-item at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(3000)

        ss(page, "P44_04_after_thumbnail_click")

        # Check result
        result = page.evaluate("""() => {
            // Check if dialog closed
            var panel = document.querySelector('.pick-panel');
            var dialogOpen = panel && panel.getBoundingClientRect().width > 100;

            // Check for reference image in CC panel (left side, below control mode buttons)
            var refImg = null;
            for (const img of document.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                // CC panel is ~60-350 x. Reference preview appears below Pick Image.
                if (r.x > 60 && r.x < 350 && r.y > 550 && r.y < 850
                    && r.width > 30 && r.height > 20) {
                    refImg = {
                        src: (img.src || '').substring(0, 120),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                    break;
                }
            }

            // Also check for any new elements near the Pick Image button area
            var newElements = [];
            for (const el of document.querySelectorAll('img, .ref-image, .reference-preview, [class*="ref"]')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 350 && r.y > 500 && r.y < 850 && r.width > 20) {
                    newElements.push({
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        src: el.src ? el.src.substring(0, 80) : '',
                    });
                }
            }

            return {dialogOpen: dialogOpen, refImg: refImg, newElements: newElements};
        }""")
        print(f"  Dialog open: {result['dialogOpen']}", flush=True)
        print(f"  Reference image: {result['refImg']}", flush=True)
        print(f"  New elements near ref area ({len(result['newElements'])}):", flush=True)
        for el in result['newElements']:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes']}' src='{el['src'][:50]}'", flush=True)

        if result['refImg']:
            print("\n  *** CANVAS IMAGE SELECTED AS REFERENCE! ***", flush=True)
        elif not result['dialogOpen']:
            print("\n  Dialog closed but no reference preview found. Scrolling CC panel...", flush=True)
            # The reference might be below the visible area — scroll the CC panel
            page.evaluate("""() => {
                var panel = document.querySelector('.gen-config-form') || document.querySelector('.left-panel-content');
                if (panel) panel.scrollTop = panel.scrollHeight;
            }""")
            page.wait_for_timeout(1000)
            ss(page, "P44_05_scrolled")

            # Check again with wider range
            ref_after_scroll = page.evaluate("""() => {
                for (const img of document.querySelectorAll('img')) {
                    var r = img.getBoundingClientRect();
                    if (r.x > 60 && r.x < 350 && r.width > 30 && r.height > 20
                        && r.y > 300) {
                        return {
                            src: (img.src || '').substring(0, 120),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        };
                    }
                }
                return null;
            }""")
            print(f"  Reference after scroll: {ref_after_scroll}", flush=True)

    # ============================================================
    #  STRATEGY 5: Investigate Vue click handler on button.upload
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STRATEGY 5: Inspect click handler on upload button", flush=True)
    print("=" * 60, flush=True)

    # Reopen dialog if closed
    dialog_open2 = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        return panel && panel.getBoundingClientRect().width > 100;
    }""")
    if not dialog_open2:
        print("  Reopening dialog...", flush=True)
        open_cc_reference_pick(page)
        page.wait_for_timeout(2000)

    # Monkey-patch createElement to intercept input[type=file] creation
    print("  5a: Monkey-patching createElement to intercept file input...", flush=True)
    page.evaluate("""() => {
        var origCreate = document.createElement.bind(document);
        window.__interceptedInputs = [];
        document.createElement = function(tag) {
            var el = origCreate(tag);
            if (tag.toLowerCase() === 'input') {
                // Watch for type being set to 'file'
                var origSetAttr = el.setAttribute.bind(el);
                el.setAttribute = function(name, value) {
                    if (name === 'type' && value === 'file') {
                        window.__interceptedInputs.push({
                            time: Date.now(),
                            accept: el.accept || '',
                            stack: new Error().stack.substring(0, 500),
                        });
                    }
                    return origSetAttr(name, value);
                };
                // Also watch the type property
                var desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'type');
                if (desc && desc.set) {
                    Object.defineProperty(el, 'type', {
                        set: function(val) {
                            if (val === 'file') {
                                window.__interceptedInputs.push({
                                    time: Date.now(),
                                    accept: el.accept || '',
                                    method: 'property',
                                    stack: new Error().stack.substring(0, 500),
                                });
                            }
                            desc.set.call(el, val);
                        },
                        get: function() { return desc.get.call(el); },
                    });
                }
            }
            return el;
        };
    }""")

    # Now click the upload button again
    print("  5b: Clicking upload button with monkey-patch active...", flush=True)
    page.evaluate("""() => {
        var btn = document.querySelector('.pick-panel button.upload');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    intercepted = page.evaluate("() => window.__interceptedInputs || []")
    print(f"\n  Intercepted file inputs: {len(intercepted)}", flush=True)
    for inp in intercepted:
        print(f"    time={inp.get('time')} accept='{inp.get('accept','')}'", flush=True)
        if inp.get('stack'):
            # Print first few lines of stack
            for line in inp['stack'].split('\n')[:5]:
                print(f"      {line.strip()}", flush=True)

    # Also check if an input was created and removed quickly
    all_inputs_now = page.evaluate("""() => {
        var items = [];
        for (const inp of document.querySelectorAll('input')) {
            items.push({type: inp.type, display: window.getComputedStyle(inp).display});
        }
        return items;
    }""")
    print(f"\n  Current inputs: {len(all_inputs_now)}", flush=True)
    for inp in all_inputs_now[:5]:
        print(f"    type={inp['type']} display={inp['display']}", flush=True)

    # Restore createElement
    page.evaluate("() => { delete document.createElement; }")

    ss(page, "P44_06_final")
    print(f"\n\n===== PHASE 44 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
