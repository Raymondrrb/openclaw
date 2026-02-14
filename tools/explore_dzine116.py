"""Phase 116: Fix Ray selection via direct JS click on hidden list element.
P115 found: .c-character-list exists at 0x0 with Ray text in DOM.
The popup doesn't render visually when "Choose a Character" is JS-clicked.

Approach:
  1) JS-click hidden Ray button in .c-character-list
  2) If that fails, force the list visible then mouse.click
  3) If that fails, try using page.mouse.click on "Choose a Character" button
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
    #  STEP 1: Open Consistent Character panel
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
    #  STEP 2: APPROACH A — JS click hidden Ray button directly
    # ============================================================
    print("\n=== STEP 2: Approach A — JS click hidden Ray ===", flush=True)

    click_result_a = page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (!list) return {error: 'no .c-character-list'};

        // Find Ray item
        for (var item of list.querySelectorAll('.item, button')) {
            var text = (item.innerText || '').trim();
            if (text === 'Ray' || text.startsWith('Ray')) {
                // Try click
                item.click();
                return {
                    clicked: true,
                    strategy: 'item.click()',
                    tag: item.tagName,
                    class: (item.className || '').toString().substring(0, 60),
                    text: text.substring(0, 20),
                };
            }
        }

        // Also try direct text node children
        for (var el of list.querySelectorAll('*')) {
            var text = (el.textContent || '').trim();
            var childText = '';
            for (var n of el.childNodes) {
                if (n.nodeType === 3) childText += n.textContent.trim();
            }
            if (childText === 'Ray' || text === 'Ray') {
                // Walk up to find clickable parent
                var target = el;
                while (target && target !== list && target.tagName !== 'BUTTON') {
                    target = target.parentElement;
                }
                if (target && target !== list) {
                    target.click();
                    return {
                        clicked: true,
                        strategy: 'parent-walk.click()',
                        tag: target.tagName,
                        class: (target.className || '').toString().substring(0, 60),
                    };
                }
                // Fallback: click the element itself
                el.click();
                return {
                    clicked: true,
                    strategy: 'el.click()',
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                };
            }
        }

        return {error: 'Ray not found in list', listText: (list.innerText || '').substring(0, 200)};
    }""")
    print(f"  Result A: {json.dumps(click_result_a)}", flush=True)
    page.wait_for_timeout(2000)

    # Check if Ray is now selected
    check_a = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var gen = panel.querySelector('.generative');
        var text = (panel.innerText || '');
        return {
            warning: text.includes('Please choose') ? 'choose' : (text.includes('Please enter') ? 'prompt' : 'none'),
            genDisabled: gen ? gen.disabled : true,
            topText: text.substring(0, 100),
        };
    }""")
    print(f"  Check A: {json.dumps(check_a)}", flush=True)

    if check_a.get('warning') == 'choose':
        # ============================================================
        #  STEP 3: APPROACH B — Force list visible + mouse click
        # ============================================================
        print("\n=== STEP 3: Approach B — Force list visible ===", flush=True)

        # Make the character list visible
        force_result = page.evaluate("""() => {
            var list = document.querySelector('.c-character-list');
            if (!list) return {error: 'no list'};

            // Force display
            list.style.cssText = 'display: block !important; position: fixed !important; left: 372px !important; top: 77px !important; width: 240px !important; height: 400px !important; z-index: 99999 !important; background: #333 !important; opacity: 1 !important; visibility: visible !important; overflow: auto !important;';

            // Also fix parent containers
            var parent = list.parentElement;
            while (parent && parent !== document.body) {
                var style = window.getComputedStyle(parent);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    parent.style.display = 'block';
                    parent.style.visibility = 'visible';
                    parent.style.opacity = '1';
                }
                parent = parent.parentElement;
            }

            // Check if items are now visible
            var items = [];
            for (var item of list.querySelectorAll('.item, button')) {
                var r = item.getBoundingClientRect();
                items.push({
                    text: (item.innerText || '').trim().substring(0, 20),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.width > 0 && r.height > 0,
                });
            }

            var lr = list.getBoundingClientRect();
            return {
                listVisible: lr.width > 0,
                listRect: {x: Math.round(lr.x), y: Math.round(lr.y), w: Math.round(lr.width), h: Math.round(lr.height)},
                items: items,
            };
        }""")
        print(f"  Force result: list visible={force_result.get('listVisible')}", flush=True)
        print(f"  List rect: {json.dumps(force_result.get('listRect'))}", flush=True)
        print(f"  Items ({len(force_result.get('items', []))}):", flush=True)
        for item in force_result.get('items', []):
            print(f"    '{item['text']}' ({item['x']},{item['y']}) {item['w']}x{item['h']} vis={item['visible']}", flush=True)

        ss(page, "P116_01_forced_list")

        # Find and click Ray with mouse
        ray_items = [i for i in force_result.get('items', []) if 'Ray' in i.get('text', '') and i.get('visible')]
        if ray_items:
            r = ray_items[0]
            cx = r['x'] + r['w'] // 2
            cy = r['y'] + r['h'] // 2
            print(f"  Mouse clicking Ray at ({cx},{cy})", flush=True)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(2000)
        else:
            # Even forced, items might not be visible
            # Try clicking in the list area where Ray should be (last item)
            # From P112: Ray was at index 5 (6th item) at y=425, each item ~52px
            lr = force_result.get('listRect', {})
            if lr.get('w', 0) > 0:
                # Ray is the last item
                ray_y = lr['y'] + 350  # Approximate based on 6th item
                print(f"  Trying mouse click at ({lr['x'] + 120},{ray_y})", flush=True)
                page.mouse.click(lr['x'] + 120, ray_y)
                page.wait_for_timeout(2000)

        # Check selection
        check_b = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {error: 'no panel'};
            var gen = panel.querySelector('.generative');
            var text = (panel.innerText || '');
            return {
                warning: text.includes('Please choose') ? 'choose' : (text.includes('Please enter') ? 'prompt' : 'none'),
                genDisabled: gen ? gen.disabled : true,
            };
        }""")
        print(f"  Check B: {json.dumps(check_b)}", flush=True)

        # Reset the forced style
        page.evaluate("""() => {
            var list = document.querySelector('.c-character-list');
            if (list) list.style.cssText = '';
        }""")

    if check_a.get('warning') == 'choose':
        # ============================================================
        #  STEP 4: APPROACH C — Use mouse.click on "Choose a Character"
        # ============================================================
        print("\n=== STEP 4: Approach C — mouse.click Choose a Character ===", flush=True)

        # Get exact button position
        choose_btn = page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Choose a Character' && r.width > 80) {
                    return {
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width),
                    };
                }
            }
            return null;
        }""")
        print(f"  Choose btn: {json.dumps(choose_btn)}", flush=True)

        if choose_btn:
            # Use real mouse click (not JS click)
            page.mouse.click(choose_btn['x'], choose_btn['y'])
            page.wait_for_timeout(2000)

            ss(page, "P116_02_mouse_choose")

            # Check if character list appeared
            list_check = page.evaluate("""() => {
                var list = document.querySelector('.c-character-list');
                if (!list) return {error: 'no list'};
                var r = list.getBoundingClientRect();

                // Also check for ANY new visible popup/dropdown
                var popups = [];
                for (var el of document.querySelectorAll('[class*="popup"], [class*="dropdown"], [class*="list"], [class*="selector"]')) {
                    var pr = el.getBoundingClientRect();
                    if (pr.width > 100 && pr.height > 100 && pr.x > 300) {
                        popups.push({
                            class: (el.className || '').toString().substring(0, 60),
                            x: Math.round(pr.x), y: Math.round(pr.y),
                            w: Math.round(pr.width), h: Math.round(pr.height),
                            text: (el.innerText || '').substring(0, 100),
                        });
                    }
                }

                return {
                    listX: Math.round(r.x), listY: Math.round(r.y),
                    listW: Math.round(r.width), listH: Math.round(r.height),
                    listVisible: r.width > 0,
                    popups: popups,
                };
            }""")
            print(f"  List after mouse click: {json.dumps(list_check)}", flush=True)

            if list_check.get('listVisible'):
                # Great! Now find and click Ray
                ray_click = page.evaluate("""() => {
                    var list = document.querySelector('.c-character-list');
                    for (var item of list.querySelectorAll('.item, button')) {
                        var text = (item.innerText || '').trim();
                        var r = item.getBoundingClientRect();
                        if (text.startsWith('Ray') && r.width > 50) {
                            return {
                                x: Math.round(r.x + r.width/2),
                                y: Math.round(r.y + r.height/2),
                                text: text,
                            };
                        }
                    }
                    return null;
                }""")
                if ray_click:
                    print(f"  Found Ray at ({ray_click['x']},{ray_click['y']})", flush=True)
                    page.mouse.click(ray_click['x'], ray_click['y'])
                    page.wait_for_timeout(2000)

            elif list_check.get('popups'):
                # Try clicking in a popup
                for popup in list_check['popups']:
                    if 'Ray' in popup.get('text', ''):
                        print(f"  Found Ray in popup: {popup['text'][:50]}", flush=True)
                        # Search for Ray position within popup
                        break

    # ============================================================
    #  STEP 5: Final check + generate if ready
    # ============================================================
    print("\n=== STEP 5: Final state ===", flush=True)

    final = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var gen = panel.querySelector('.generative');
        var text = (panel.innerText || '');
        return {
            warning: text.includes('Please choose') ? 'choose' :
                     text.includes('Please enter') ? 'prompt' : 'none',
            genDisabled: gen ? gen.disabled : true,
            topText: text.substring(0, 200),
        };
    }""")
    print(f"  Final: {json.dumps(final)}", flush=True)

    ss(page, "P116_03_final")

    # If character selected, type prompt and generate
    if final.get('warning') != 'choose':
        print("\n  CHARACTER SELECTED! Typing prompt and generating...", flush=True)

        ta = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var ta = panel.querySelector('.custom-textarea, textarea, .prompt-textarea');
            if (!ta) return null;
            var r = ta.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        if ta:
            page.mouse.click(ta['x'], ta['y'])
            page.wait_for_timeout(300)
            page.keyboard.press("Meta+a")
            page.keyboard.type("YouTube host presenting headphones, professional studio, confident", delay=10)
            page.wait_for_timeout(1000)

        # Click Generate
        gen = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var gen = panel.querySelector('.generative');
            if (!gen || gen.disabled) return null;
            var r = gen.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), text: (gen.innerText||'').trim()};
        }""")

        if gen:
            initial = page.evaluate("() => document.querySelectorAll('.result-item').length")
            print(f"  Generating ({gen['text']})...", flush=True)
            page.mouse.click(gen['x'], gen['y'])

            for i in range(40):
                elapsed = (i + 1) * 3
                check = page.evaluate("""(ic) => {
                    var results = document.querySelectorAll('.result-item');
                    var nc = results.length;
                    var n = results[0];
                    var nimg = n ? n.querySelector('img') : null;
                    var loaded = nimg ? nimg.naturalWidth > 0 : false;
                    var pct = null;
                    for (var e of document.querySelectorAll('.result-item')) {
                        var m = (e.innerText||'').match(/(\\d+)%/);
                        if (m) { pct = m[1]+'%'; break; }
                    }
                    return {new: nc-ic, loaded: loaded, pct: pct};
                }""", initial)

                if check.get('new', 0) > 0 and check.get('loaded'):
                    print(f"  Image at {elapsed}s!", flush=True)
                    break
                if i % 3 == 0:
                    print(f"  ...{elapsed}s new={check.get('new',0)} pct={check.get('pct')}", flush=True)
                page.wait_for_timeout(3000)

            ss(page, "P116_04_generation")
        else:
            print("  Generate still disabled after prompt", flush=True)
    else:
        print("\n  Character still not selected. Investigating DOM structure...", flush=True)

        # Deep DOM investigation of character list
        dom_info = page.evaluate("""() => {
            var list = document.querySelector('.c-character-list');
            if (!list) return {error: 'no list'};

            // Full DOM tree up to body
            var ancestry = [];
            var el = list;
            while (el && el !== document.body) {
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                ancestry.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 40),
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    overflow: style.overflow,
                    position: style.position,
                    w: Math.round(r.width), h: Math.round(r.height),
                    x: Math.round(r.x), y: Math.round(r.y),
                });
                el = el.parentElement;
            }

            // List children structure
            var children = [];
            for (var child of list.children) {
                var cr = child.getBoundingClientRect();
                children.push({
                    tag: child.tagName,
                    class: (child.className || '').toString().substring(0, 60),
                    text: (child.innerText || '').substring(0, 50),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                    display: window.getComputedStyle(child).display,
                });
            }

            return {ancestry: ancestry, children: children};
        }""")

        print("  Ancestry (child → parent):", flush=True)
        for a in dom_info.get('ancestry', []):
            print(f"    <{a['tag']}> .{a['class'][:30]} display={a['display']} vis={a['visibility']} opacity={a['opacity']} ({a['x']},{a['y']}) {a['w']}x{a['h']}", flush=True)

        print("  Children:", flush=True)
        for c in dom_info.get('children', []):
            print(f"    <{c['tag']}> .{c['class'][:40]} display={c['display']} '{c['text'][:30]}' {c['w']}x{c['h']}", flush=True)

    print(f"\n\n===== PHASE 116 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
