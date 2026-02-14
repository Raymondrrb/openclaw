"""Phase 115: Fix Ray character selection (timing) + test clipboard upload.
P114 findings:
- .c-character-list is in DOM but invisible (0x0) — only visible as popup
- "Choose a Character" opens flyout panel at x~372 that disappears on blur
- ZERO input[type="file"] on entire page
- drag-drop containers exist but mostly invisible
- Credits: 8,856

Goal: 1) Fix Ray selection by clicking "Choose a Character" then immediately
         finding and clicking Ray in the popup before it closes
      2) Test clipboard paste for image upload (Cmd+V)
      3) Test if Upload sidebar uses showOpenFilePicker()
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
    print("\n=== STEP 1: Open Consistent Character ===", flush=True)

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
    #  STEP 2: Click "Choose a Character" then screenshot to see popup
    # ============================================================
    print("\n=== STEP 2: Open character chooser + screenshot ===", flush=True)

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
    page.wait_for_timeout(1500)

    # Immediately screenshot to capture the popup
    ss(page, "P115_01_character_popup_open")

    # Now map ALL visible elements in the character popup area (x > 300)
    popup_items = page.evaluate("""() => {
        var items = [];

        // Scan the right side for popup content
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            // Character popup appears around x=350-650, y=70-470
            if (r.x < 340 || r.x > 660 || r.y < 50 || r.y > 500) continue;
            if (r.width < 30 || r.height < 15 || r.width > 260) continue;

            var text = (el.innerText || '').trim();
            if (text.length === 0) continue;
            // Skip elements with too many children (containers)
            if (el.children.length > 3) continue;

            items.push({
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                text: text.substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                clickable: el.tagName === 'BUTTON' || el.onclick || el.getAttribute('role') === 'button',
            });
        }

        // Also check specifically for character list
        var clist = document.querySelector('.c-character-list');
        var clistInfo = null;
        if (clist) {
            var r = clist.getBoundingClientRect();
            clistInfo = {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                visible: r.width > 0,
            };
        }

        return {items: items, clist: clistInfo};
    }""")

    print(f"  Character list: {json.dumps(popup_items.get('clist'))}", flush=True)
    print(f"\n  Popup items ({len(popup_items.get('items', []))}):", flush=True)
    for item in popup_items.get('items', [])[:20]:
        print(f"    <{item['tag']}> .{item['class'][:40]} '{item['text'][:25]}' ({item['x']},{item['y']}) {item['w']}x{item['h']} click={item['clickable']}", flush=True)

    # ============================================================
    #  STEP 3: Click Ray in the popup using direct mouse click
    # ============================================================
    print("\n=== STEP 3: Click Ray ===", flush=True)

    # Find Ray in the popup items
    ray_items = [i for i in popup_items.get('items', []) if 'Ray' in i.get('text', '') and 'Aspect' not in i.get('text', '')]

    if ray_items:
        ray = ray_items[0]
        # Click the item or its parent (prefer the larger clickable area)
        target_x = ray['x'] + ray['w'] // 2
        target_y = ray['y'] + ray['h'] // 2
        print(f"  Clicking Ray at ({target_x},{target_y}) - '{ray['text']}'", flush=True)
        page.mouse.click(target_x, target_y)
        page.wait_for_timeout(2000)
    else:
        # Try clicking through "Choose a Character" button then use locator
        print("  Ray not in popup items. Using Playwright locator...", flush=True)

        # Re-open the character chooser
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button, [class*="choose"]')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Choose a Character')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(1500)

        # Try using page.locator to find Ray
        ray_loc = page.locator('text="Ray"')
        count = ray_loc.count()
        print(f"  Locator 'text=Ray' count: {count}", flush=True)

        if count > 0:
            for i in range(count):
                box = ray_loc.nth(i).bounding_box()
                if box and box['x'] > 300 and box['width'] < 300:
                    print(f"  Ray locator [{i}] at ({box['x']},{box['y']}) {box['width']}x{box['height']}", flush=True)
                    ray_loc.nth(i).click()
                    page.wait_for_timeout(2000)
                    break
        else:
            # Last resort: try clicking button text matching
            page.locator('button:has-text("Ray")').first.click(timeout=3000)
            page.wait_for_timeout(2000)

    ss(page, "P115_02_after_ray_click")

    # ============================================================
    #  STEP 4: Check if Ray is now selected
    # ============================================================
    print("\n=== STEP 4: Verify Ray selection ===", flush=True)

    selected = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        var fullText = (panel.innerText || '');
        var hasChoose = fullText.includes('Choose a Character');

        // Check for character name/avatar near the "Choose" button
        var charArea = null;
        for (var el of panel.querySelectorAll('[class*="char"], [class*="avatar"], [class*="selected-char"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 20 && r.x < 300) {
                charArea = {
                    class: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                };
            }
        }

        // Check Generate button
        var gen = panel.querySelector('.generative');
        return {
            hasChoose: hasChoose,
            charArea: charArea,
            genDisabled: gen ? gen.disabled : true,
            genText: gen ? (gen.innerText || '').trim() : '',
            warning: fullText.includes('Please choose') ? 'choose' : (fullText.includes('Please enter') ? 'prompt' : null),
            topText: fullText.substring(0, 150),
        };
    }""")
    print(f"  Selection result: {json.dumps(selected, indent=2)}", flush=True)

    # If still not selected, try one more approach
    if selected.get('warning') == 'choose':
        print("\n  Still not selected. Trying: open chooser + find visible Ray + click...", flush=True)

        # Open chooser
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Choose a Character')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(2000)

        # Take screenshot to see what the popup looks like
        ss(page, "P115_03_chooser_open")

        # Try to find ANY visible item with text "Ray"
        found_ray = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.textContent || '').trim();
                var r = el.getBoundingClientRect();
                // Only visible elements
                if (r.width === 0 || r.height === 0) continue;
                // Only elements where the DIRECT text content is "Ray"
                if (el.childElementCount === 0 && text === 'Ray') {
                    results.push({
                        tag: el.tagName,
                        class: (el.className || '').toString().substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        parentTag: el.parentElement?.tagName || '',
                        parentClass: (el.parentElement?.className || '').toString().substring(0, 60),
                        parentX: Math.round(el.parentElement?.getBoundingClientRect()?.x || 0),
                        parentY: Math.round(el.parentElement?.getBoundingClientRect()?.y || 0),
                        parentW: Math.round(el.parentElement?.getBoundingClientRect()?.width || 0),
                        parentH: Math.round(el.parentElement?.getBoundingClientRect()?.height || 0),
                    });
                }
            }
            return results;
        }""")
        print(f"  Visible 'Ray' elements: {json.dumps(found_ray, indent=2)}", flush=True)

        if found_ray:
            # Click the parent element (which is likely the button)
            r = found_ray[0]
            if r['parentW'] > 30:
                cx = r['parentX'] + r['parentW'] // 2
                cy = r['parentY'] + r['parentH'] // 2
            else:
                cx = r['x'] + r['w'] // 2
                cy = r['y'] + r['h'] // 2
            print(f"  Clicking at ({cx},{cy})...", flush=True)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(2000)

            # Check again
            check = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                var gen = panel.querySelector('.generative');
                return {
                    warning: (panel.innerText || '').includes('Please choose') ? 'choose' : 'ok',
                    genDisabled: gen ? gen.disabled : true,
                    topText: (panel.innerText || '').substring(0, 100),
                };
            }""")
            print(f"  After click: {json.dumps(check)}", flush=True)

    ss(page, "P115_04_final_state")

    # ============================================================
    #  STEP 5: If Ray selected, generate!
    # ============================================================
    gen_check = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var gen = panel.querySelector('.generative');
        if (!gen) return null;
        var r = gen.getBoundingClientRect();
        return {disabled: gen.disabled, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
    }""")

    if gen_check and gen_check.get('disabled'):
        # Type prompt first
        ta = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var ta = panel.querySelector('.custom-textarea, textarea, .prompt-textarea');
            if (!ta) return null;
            var r = ta.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        if ta:
            page.mouse.click(ta['x'], ta['y'])
            page.wait_for_timeout(300)
            page.keyboard.press("Meta+a")
            page.keyboard.type("YouTube host presenting wireless headphones, studio, professional", delay=10)
            page.wait_for_timeout(500)

        # Recheck
        gen_check = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var gen = panel.querySelector('.generative');
            if (!gen) return null;
            var r = gen.getBoundingClientRect();
            return {disabled: gen.disabled, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), text: (gen.innerText||'').trim()};
        }""")

    print(f"\n=== STEP 5: Generate ===", flush=True)
    print(f"  Gen state: {json.dumps(gen_check)}", flush=True)

    if gen_check and not gen_check.get('disabled'):
        initial = page.evaluate("() => document.querySelectorAll('.result-item').length")
        print(f"  Generating! Initial results: {initial}", flush=True)
        page.mouse.click(gen_check['x'], gen_check['y'])

        for i in range(30):
            elapsed = (i + 1) * 3
            check = page.evaluate("""(ic) => {
                var results = document.querySelectorAll('.result-item');
                var nc = results.length;
                var n = results[0];
                var ntext = n ? (n.innerText||'').substring(0,60) : '';
                var nimg = n ? n.querySelector('img') : null;
                var loaded = nimg ? nimg.naturalWidth > 0 : false;
                var pct = null;
                for (var e of document.querySelectorAll('.result-item')) {
                    var m = (e.innerText||'').match(/(\\d+)%/);
                    if (m) { pct = m[1]+'%'; break; }
                }
                return {new: nc-ic, loaded: loaded, pct: pct, text: ntext};
            }""", initial)

            if check.get('new', 0) > 0 and check.get('loaded'):
                print(f"  Image ready at {elapsed}s!", flush=True)
                break
            if i % 3 == 0:
                print(f"  ...{elapsed}s new={check.get('new',0)} pct={check.get('pct')} text='{check.get('text','')[:40]}'", flush=True)
            page.wait_for_timeout(3000)

        ss(page, "P115_05_generation_result")
    else:
        print("  Generate still disabled — character not selected.", flush=True)

    # ============================================================
    #  STEP 6: Upload — test sidebar Upload with CDP file intercept
    # ============================================================
    print("\n=== STEP 6: Upload via CDP ===", flush=True)

    # Check if Dzine uses window.showOpenFilePicker (modern File System Access API)
    uses_picker = page.evaluate("""() => {
        return {
            hasShowOpenFilePicker: typeof window.showOpenFilePicker === 'function',
            hasShowSaveFilePicker: typeof window.showSaveFilePicker === 'function',
        };
    }""")
    print(f"  File System Access API: {json.dumps(uses_picker)}", flush=True)

    # Check all event listeners on the Upload sidebar icon
    upload_icon_info = page.evaluate("""() => {
        var icon = document.querySelector('.tool-item.import');
        if (!icon) return null;
        var r = icon.getBoundingClientRect();
        return {
            class: (icon.className || '').toString(),
            x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
            w: Math.round(r.width), h: Math.round(r.height),
            children: Array.from(icon.children).map(c => ({
                tag: c.tagName,
                class: (c.className||'').toString().substring(0,40),
            })),
        };
    }""")
    print(f"  Upload icon: {json.dumps(upload_icon_info)}", flush=True)

    # Try intercepting the file chooser by overriding showOpenFilePicker
    print("\n  Overriding showOpenFilePicker to detect usage...", flush=True)
    page.evaluate("""() => {
        window._filePickerCalled = false;
        var orig = window.showOpenFilePicker;
        window.showOpenFilePicker = function() {
            window._filePickerCalled = true;
            console.log('showOpenFilePicker intercepted!');
            return orig ? orig.apply(this, arguments) : Promise.reject(new Error('cancelled'));
        };
    }""")

    # Click Upload icon
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)

    picker_called = page.evaluate("() => window._filePickerCalled")
    print(f"  showOpenFilePicker called: {picker_called}", flush=True)

    # Check if clicking Upload opened the Assets panel
    check_after_upload = page.evaluate("""() => {
        var panels = [];
        for (var el of document.querySelectorAll('.panels.show, .c-gen-config.show')) {
            panels.push((el.className || '').toString().substring(0, 60));
        }
        var text = document.querySelector('.panels.show');
        return {
            panels: panels,
            text: text ? (text.innerText || '').substring(0, 100) : null,
        };
    }""")
    print(f"  After Upload click: {json.dumps(check_after_upload)}", flush=True)

    ss(page, "P115_06_upload_test")

    print(f"\n\n===== PHASE 115 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
