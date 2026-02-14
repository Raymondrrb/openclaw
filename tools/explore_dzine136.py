"""Phase 136: Results panel Enhance buttons + unlock layer + codification test.

P135 discovered: Results panel has "Enhance & Upscale 1 2 3 4" buttons for each result.
These might bypass the canvas layer selection requirement entirely.

Also: Layer 1 is LOCKED. Try unlocking via lock icon in Layers panel.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path.home() / "Downloads"


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(8):
        found = False
        try:
            fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
            if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=500):
                fit_btn.first.click()
                page.wait_for_timeout(1000)
                found = True
                continue
        except Exception:
            pass
        try:
            cb = page.locator('text=Do not show again')
            if cb.count() > 0 and cb.first.is_visible(timeout=300):
                cb.first.click()
                page.wait_for_timeout(300)
        except Exception:
            pass
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip",
                      "Later", "Continue", "OK", "Cancel"]:
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


def close_all_panels(page):
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
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
    print("=" * 60, flush=True)
    print("PHASE 136: Results panel Enhance + unlock layer", flush=True)
    print("=" * 60, flush=True)

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # Find the existing canvas from P135
    dzine_pages = [p for p in ctx.pages if "dzine.ai/canvas" in (p.url or "")]
    if not dzine_pages:
        print("  No canvas page found from P135! Opening last canvas...", flush=True)
        page = ctx.new_page()
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("https://www.dzine.ai/canvas?id=19861056", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        close_dialogs(page)
    else:
        page = dzine_pages[0]
        page.set_viewport_size({"width": 1440, "height": 900})
        page.bring_to_front()
        page.wait_for_timeout(1000)

    print(f"  Current URL: {page.url}", flush=True)

    # ============================================================
    #  TEST 1: Results panel Enhance buttons
    # ============================================================
    print("\n=== TEST 1: Results panel Enhance & Upscale buttons ===", flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Map out the action buttons in the Results panel
    actions_map = page.evaluate("""() => {
        var result = {};
        // Find all text elements that are action labels
        var labels = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 700 && r.width > 0 && r.width < 300) {
                if (text === 'Chat Editor' || text === 'Image Editor' || text === 'AI Video' ||
                    text === 'Lip Sync' || text === 'Expression Edit' || text === 'Face Swap' ||
                    text === 'Enhance & Upscale') {
                    labels.push({
                        text: text,
                        x: Math.round(r.x),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width),
                        h: Math.round(r.height)
                    });
                }
            }
        }
        result.labels = labels;

        // Find numbered buttons (1, 2, 3, 4) near the labels
        var numbered = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (/^[1234]$/.test(text) && r.x > 700 && r.width > 0 && r.width < 40 && r.height < 40) {
                numbered.push({
                    text: text,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                    clickable: el.tagName === 'BUTTON' || el.style.cursor === 'pointer' ||
                               el.closest('button') !== null
                });
            }
        }
        result.numbered = numbered;

        return result;
    }""")
    print(f"  Action labels: {len(actions_map.get('labels', []))}", flush=True)
    for label in actions_map.get('labels', []):
        print(f"    {label['text']} at ({label['x']}, {label['y']})", flush=True)

    print(f"  Numbered buttons: {len(actions_map.get('numbered', []))}", flush=True)
    for nb in actions_map.get('numbered', [])[:12]:
        print(f"    [{nb['text']}] at ({nb['x']}, {nb['y']}) tag={nb['tag']} clickable={nb['clickable']}", flush=True)

    ss(page, "P136_01_results_panel")

    # Find the Enhance & Upscale numbered buttons
    enhance_label = None
    for label in actions_map.get('labels', []):
        if 'Enhance' in label['text']:
            enhance_label = label
            break

    if enhance_label:
        # Find numbered buttons near the Enhance label (within ~30px y range)
        enhance_y = enhance_label['y']
        enhance_buttons = [
            nb for nb in actions_map.get('numbered', [])
            if abs(nb['y'] - enhance_y) < 30
        ]
        print(f"\n  Enhance buttons near y={enhance_y}: {len(enhance_buttons)}", flush=True)
        for eb in enhance_buttons:
            print(f"    [{eb['text']}] at ({eb['x']}, {eb['y']})", flush=True)

        if enhance_buttons:
            # Click button "1" to enhance the first result
            btn = enhance_buttons[0]
            print(f"\n  Clicking Enhance button [{btn['text']}] at ({btn['x']}, {btn['y']})...", flush=True)
            page.mouse.click(btn['x'], btn['y'])
            page.wait_for_timeout(3000)
            close_dialogs(page)

            ss(page, "P136_02_after_enhance_click")

            # Check what happened — did the Enhance panel open? Did processing start?
            state = page.evaluate("""() => {
                var result = {};

                // Check for Enhance panel
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Enhance & Upscale') {
                        var r = el.getBoundingClientRect();
                        if (r.x < 300 && r.width > 0) {
                            result.panel_open = true;
                            break;
                        }
                    }
                }

                // Check for layer warning
                for (var el of document.querySelectorAll('*')) {
                    if ((el.innerText || '').trim() === 'Please select one layer on canvas') {
                        result.layer_warning = true;
                        break;
                    }
                }

                // Check for progress/processing
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('Processing') || text.includes('Enhancing') ||
                        text.match(/^\d{1,3}%$/)) {
                        result.processing = text;
                        break;
                    }
                }

                // Check for new result images
                var resultImgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/"]');
                result.result_count = resultImgs.length;

                return result;
            }""")
            print(f"  State after click: {json.dumps(state)}", flush=True)

            # If Enhance panel opened, check for Upscale button
            if state.get('panel_open'):
                upscale_state = page.evaluate("""() => {
                    for (var b of document.querySelectorAll('button')) {
                        var text = (b.innerText || '').trim();
                        if (text === 'Upscale') {
                            return {
                                found: true,
                                disabled: b.disabled,
                                visible: b.getBoundingClientRect().width > 0,
                                x: Math.round(b.getBoundingClientRect().x + b.getBoundingClientRect().width/2),
                                y: Math.round(b.getBoundingClientRect().y + b.getBoundingClientRect().height/2)
                            };
                        }
                    }
                    return {found: false};
                }""")
                print(f"  Upscale button: {json.dumps(upscale_state)}", flush=True)

                if upscale_state.get('found') and not upscale_state.get('disabled') and not state.get('layer_warning'):
                    print("  Enhance WORKS from Results panel!", flush=True)

                    # Click Upscale
                    page.mouse.click(upscale_state['x'], upscale_state['y'])
                    page.wait_for_timeout(5000)
                    close_dialogs(page)

                    # Wait for result
                    start = time.time()
                    while time.time() - start < 90:
                        elapsed = int(time.time() - start)
                        close_dialogs(page)
                        done = page.evaluate("""() => {
                            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/"]');
                            for (var img of imgs) {
                                if (img.src.includes('enhance')) return img.src;
                            }
                            return null;
                        }""")
                        if done:
                            print(f"  Enhance complete in {elapsed}s!", flush=True)
                            break
                        if elapsed % 10 == 0:
                            print(f"  Enhance: {elapsed}s...", flush=True)
                        page.wait_for_timeout(3000)

                    ss(page, "P136_03_enhanced")

    # ============================================================
    #  TEST 2: Unlock layer and try Enhance from sidebar
    # ============================================================
    print("\n=== TEST 2: Unlock layer + sidebar Enhance ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    # Switch to Layers tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Layers') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Find locked layers and their lock icons
    lock_info = page.evaluate("""() => {
        var result = [];
        var items = document.querySelectorAll('.layer-item');
        for (var item of items) {
            var r = item.getBoundingClientRect();
            if (r.width === 0) continue;  // skip zero-size duplicates

            var isLocked = item.classList.contains('locked');
            var text = (item.innerText || '').trim().substring(0, 30);

            // Find lock icon within this layer item
            var lockIcons = [];
            for (var child of item.querySelectorAll('*')) {
                var cls = (child.className || '').toString();
                if (cls.includes('lock') || cls.includes('ico-lock')) {
                    var cr = child.getBoundingClientRect();
                    lockIcons.push({
                        classes: cls.substring(0, 40),
                        x: Math.round(cr.x + cr.width/2),
                        y: Math.round(cr.y + cr.height/2),
                        w: Math.round(cr.width),
                        h: Math.round(cr.height)
                    });
                }
            }

            // Also check for any small clickable icon (lock/unlock toggle)
            var icons = [];
            for (var child of item.querySelectorAll('svg, i, [class*="ico"]')) {
                var cr = child.getBoundingClientRect();
                if (cr.width > 0 && cr.width < 30) {
                    icons.push({
                        tag: child.tagName,
                        classes: (child.className || '').toString().substring(0, 40),
                        x: Math.round(cr.x + cr.width/2),
                        y: Math.round(cr.y + cr.height/2)
                    });
                }
            }

            result.push({
                text: text,
                locked: isLocked,
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                lockIcons: lockIcons,
                icons: icons
            });
        }
        return result;
    }""")
    print(f"  Layers:", flush=True)
    for li in lock_info:
        print(f"    {li['text']} locked={li['locked']} icons={len(li.get('icons',[]))}", flush=True)
        for icon in li.get('icons', []):
            print(f"      icon: {icon['tag']} {icon.get('classes','')} at ({icon['x']}, {icon['y']})", flush=True)
        for lk in li.get('lockIcons', []):
            print(f"      lock: {lk['classes']} at ({lk['x']}, {lk['y']})", flush=True)

    ss(page, "P136_04_layers")

    # Try to unlock: right-click on the locked layer to get context menu
    locked_layers = [li for li in lock_info if li['locked']]
    if locked_layers:
        ll = locked_layers[0]
        print(f"\n  Trying to unlock '{ll['text']}'...", flush=True)

        # Method A: Click lock icon if found
        if ll.get('lockIcons'):
            lk = ll['lockIcons'][0]
            print(f"  Click lock icon at ({lk['x']}, {lk['y']})...", flush=True)
            page.mouse.click(lk['x'], lk['y'])
            page.wait_for_timeout(500)
        elif ll.get('icons'):
            # Try clicking each icon
            for icon in ll['icons']:
                print(f"  Click icon {icon['tag']} at ({icon['x']}, {icon['y']})...", flush=True)
                page.mouse.click(icon['x'], icon['y'])
                page.wait_for_timeout(300)

        # Check if still locked
        still_locked = page.evaluate("""() => {
            var items = document.querySelectorAll('.layer-item');
            for (var item of items) {
                var r = item.getBoundingClientRect();
                if (r.width === 0) continue;
                if (item.classList.contains('locked')) return true;
            }
            return false;
        }""")
        print(f"  Still locked after icon click: {still_locked}", flush=True)

        if still_locked:
            # Method B: Right-click for context menu
            print(f"  Right-click on layer for context menu...", flush=True)
            page.mouse.click(ll['x'], ll['y'], button="right")
            page.wait_for_timeout(1000)

            # Check for context menu
            ctx_menu = page.evaluate("""() => {
                var menus = [];
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (r.width > 0 && (text.includes('Unlock') || text.includes('Lock') ||
                        text.includes('Delete') || text.includes('Duplicate') ||
                        text.includes('Flatten') || text.includes('Merge'))) {
                        menus.push({
                            text: text.substring(0, 30),
                            x: Math.round(r.x + r.width/2),
                            y: Math.round(r.y + r.height/2)
                        });
                    }
                }
                return menus;
            }""")
            print(f"  Context menu items: {json.dumps(ctx_menu)}", flush=True)

            # Click Unlock if found
            unlock_item = next((m for m in ctx_menu if 'Unlock' in m['text'] or 'Lock' in m['text']), None)
            if unlock_item:
                print(f"  Clicking '{unlock_item['text']}' at ({unlock_item['x']}, {unlock_item['y']})...", flush=True)
                page.mouse.click(unlock_item['x'], unlock_item['y'])
                page.wait_for_timeout(500)
            else:
                # Dismiss context menu
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)

        # Method C: Try selecting the layer and pressing keyboard shortcut
        if still_locked:
            print(f"  Trying keyboard unlock (select layer + shortcut)...", flush=True)
            page.mouse.click(ll['x'], ll['y'])
            page.wait_for_timeout(300)
            # Common unlock shortcuts
            page.keyboard.press("Meta+l")  # lock/unlock toggle?
            page.wait_for_timeout(300)

        # Final check
        final_locked = page.evaluate("""() => {
            var items = document.querySelectorAll('.layer-item');
            for (var item of items) {
                var r = item.getBoundingClientRect();
                if (r.width === 0) continue;
                if (item.classList.contains('locked')) return true;
            }
            return false;
        }""")
        print(f"  Final locked state: {final_locked}", flush=True)

        if not final_locked:
            # Layer unlocked! Try Enhance now
            print("\n  Layer UNLOCKED! Trying Enhance...", flush=True)
            page.mouse.click(700, 400)  # click canvas to select layer
            page.wait_for_timeout(500)

            open_sidebar_tool(page, 628)
            page.wait_for_timeout(2000)

            warning = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    if ((el.innerText || '').trim() === 'Please select one layer on canvas') return true;
                }
                return false;
            }""")
            print(f"  Enhance warning after unlock: {warning}", flush=True)

    # ============================================================
    #  TEST 3: Export with 4x upscale (workaround for no Enhance)
    # ============================================================
    print("\n=== TEST 3: Export with 4x upscale (Enhance alternative) ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    # Click Export button
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Export') {
                var r = b.getBoundingClientRect();
                if (r.y < 40) { b.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Select PNG
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'PNG') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    # Select 4x upscale
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === '4x') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    # Check dimensions at 4x
    dimensions = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.match(/^\d{3,5}\s*[x×]\s*\d{3,5}$/)) return text;
        }
        return null;
    }""")
    print(f"  Export dimensions at 4x: {dimensions}", flush=True)

    ss(page, "P136_05_export_4x")

    # Uncheck watermark
    page.evaluate("""() => {
        var cb = document.querySelector('input[type="checkbox"]');
        if (cb && cb.checked) cb.click();
    }""")
    page.wait_for_timeout(300)

    # Export
    try:
        with page.expect_download(timeout=30000) as dl_info:
            page.evaluate("""() => {
                for (var b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').trim().includes('Export canvas')) { b.click(); return; }
                }
            }""")
        dl = dl_info.value
        export_path = str(DOWNLOAD_DIR / f"dzine_export_4x_{int(time.time())}.png")
        dl.save_as(export_path)
        size_kb = os.path.getsize(export_path) / 1024
        print(f"  Exported 4x: {os.path.basename(export_path)} ({size_kb:.1f} KB)", flush=True)
    except Exception as e:
        print(f"  Export error: {e}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  SUMMARY
    # ============================================================
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 100 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")

    print(f"\n{'='*60}", flush=True)
    print(f"PHASE 136 SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Credits: {credits}", flush=True)
    print(f"  Export 4x dimensions: {dimensions}", flush=True)

    ss(page, "P136_06_final")
    print(f"\n===== PHASE 136 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
