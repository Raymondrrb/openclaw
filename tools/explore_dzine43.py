"""Phase 43: Dump Pick Image dialog HTML + alternative upload approaches.

Need to understand the exact HTML structure of the upload zone.
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

    # Open CC panel + Reference + Pick Image (proven approach from P42)
    print("\n  Opening CC → Reference → Pick Image...", flush=True)
    page.mouse.click(40, 197)
    page.wait_for_timeout(1000)
    page.mouse.click(40, 306)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Generate Images')) { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('button')) {
            if ((el.innerText || '').trim() === 'Ray') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    # Click Reference (at known position from P42: x=251,y=567)
    page.mouse.click(285, 579)
    page.wait_for_timeout(2000)

    # Click Pick Image (at known position from P42: x=100,y=607)
    page.mouse.click(212, 627)
    page.wait_for_timeout(3000)

    ss(page, "P43_01_dialog")

    # ============================================================
    #  DUMP DIALOG HTML
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  DIALOG HTML DUMP", flush=True)
    print("=" * 60, flush=True)

    # Find the dialog modal element and dump its innerHTML
    dialog_html = page.evaluate("""() => {
        // Look for the modal/dialog container
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Pick Image') && text.includes('Drop or select')
                && text.includes('canvas')) {
                var r = el.getBoundingClientRect();
                if (r.width > 200 && r.width < 600 && r.height > 100 && r.height < 500) {
                    return {
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString(),
                        innerHTML: el.innerHTML.substring(0, 2000),
                    };
                }
            }
        }
        return null;
    }""")

    if dialog_html:
        print(f"\n  Dialog container: <{dialog_html['tag']}> ({dialog_html['x']},{dialog_html['y']}) {dialog_html['w']}x{dialog_html['h']}", flush=True)
        print(f"  Classes: {dialog_html['classes']}", flush=True)
        print(f"\n  innerHTML (first 2000 chars):", flush=True)
        print(dialog_html['innerHTML'][:2000], flush=True)
    else:
        print("  Dialog container not found. Trying broader search...", flush=True)
        # Try to get the outer HTML of any element with "Pick Image" text
        alt = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Pick Image') {
                    var parent = el.parentElement;
                    for (var i = 0; i < 5 && parent; i++) {
                        var r = parent.getBoundingClientRect();
                        if (r.width > 300 && r.height > 200) {
                            return {
                                tag: parent.tagName,
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                classes: (parent.className || '').toString(),
                                innerHTML: parent.innerHTML.substring(0, 2000),
                            };
                        }
                        parent = parent.parentElement;
                    }
                }
            }
            return null;
        }""")
        if alt:
            print(f"\n  Alternative: <{alt['tag']}> ({alt['x']},{alt['y']}) {alt['w']}x{alt['h']}", flush=True)
            print(f"  Classes: {alt['classes']}", flush=True)
            print(f"\n  innerHTML:", flush=True)
            print(alt['innerHTML'][:2000], flush=True)

    # ============================================================
    #  CHECK FOR IFRAMES AND SHADOW DOM
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  IFRAME AND SHADOW DOM CHECK", flush=True)
    print("=" * 60, flush=True)

    iframe_check = page.evaluate("""() => {
        var iframes = document.querySelectorAll('iframe');
        var shadows = [];
        for (const el of document.querySelectorAll('*')) {
            if (el.shadowRoot) {
                shadows.push({
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return {iframeCount: iframes.length, shadowRoots: shadows};
    }""")
    print(f"  Iframes: {iframe_check['iframeCount']}", flush=True)
    print(f"  Shadow roots: {len(iframe_check['shadowRoots'])}", flush=True)
    for sr in iframe_check['shadowRoots'][:5]:
        print(f"    <{sr['tag']}> c='{sr['classes']}'", flush=True)

    # ============================================================
    #  DUMP ALL ELEMENTS IN THE DIALOG AREA
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  ALL ELEMENTS IN DIALOG AREA", flush=True)
    print("=" * 60, flush=True)

    dialog_elements = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            // Dialog is centered, roughly 350-740 x, 100-400 y
            if (r.x > 320 && r.x < 760 && r.y > 90 && r.y < 420
                && r.width > 5 && r.height > 5 && r.width < 450) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 40),
                    classes: (el.className || '').toString().substring(0, 50),
                    cursor: window.getComputedStyle(el).cursor,
                    border: window.getComputedStyle(el).borderStyle,
                    onclick: el.onclick ? 'has_onclick' : '',
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y + '|' + i.w + '|' + i.h;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Dialog elements ({len(dialog_elements)}):", flush=True)
    for el in dialog_elements[:40]:
        extras = []
        if el['cursor'] != 'auto' and el['cursor'] != 'default': extras.append(f"cursor={el['cursor']}")
        if el['border'] and el['border'] != 'none': extras.append(f"border={el['border']}")
        if el['onclick']: extras.append("ONCLICK")
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}'{extra_str} '{el['text'][:25]}'", flush=True)

    # ============================================================
    #  TRY CLICKING THE DASHED AREA AND CHECK FOR FILE INPUT CREATION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  CLICK DASHED AREA + MONITOR FILE INPUTS", flush=True)
    print("=" * 60, flush=True)

    # Set up mutation observer to watch for file input creation
    page.evaluate("""() => {
        window.__newInputs = [];
        var observer = new MutationObserver(function(mutations) {
            for (var m of mutations) {
                for (var node of m.addedNodes) {
                    if (node.tagName === 'INPUT' || (node.querySelectorAll && node.querySelectorAll('input').length > 0)) {
                        var inputs = node.tagName === 'INPUT' ? [node] : [...node.querySelectorAll('input')];
                        for (var inp of inputs) {
                            window.__newInputs.push({
                                type: inp.type,
                                accept: inp.accept || '',
                                time: Date.now(),
                            });
                        }
                    }
                }
            }
        });
        observer.observe(document.body, {childList: true, subtree: true});
    }""")

    # Find and click the dashed area
    for el in dialog_elements:
        if el['border'] and 'dashed' in el['border']:
            cx = el['x'] + el['w'] // 2
            cy = el['y'] + el['h'] // 2
            print(f"  Found dashed element at ({el['x']},{el['y']}) {el['w']}x{el['h']}", flush=True)
            print(f"  Clicking at ({cx}, {cy})...", flush=True)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(2000)
            break
    else:
        # Fallback: click at approximate center of "Drop or select" text
        print("  No dashed element found. Clicking at (536, 150)...", flush=True)
        page.mouse.click(536, 150)
        page.wait_for_timeout(2000)

    # Check for new inputs
    new_inputs = page.evaluate("() => window.__newInputs || []")
    print(f"\n  New inputs after click: {len(new_inputs)}", flush=True)
    for inp in new_inputs:
        print(f"    type={inp['type']} accept={inp['accept']}", flush=True)

    # Check if a file input was created anywhere
    all_file_inputs = page.evaluate("""() => {
        var inputs = [];
        for (const inp of document.querySelectorAll('input')) {
            if (inp.type === 'file') {
                inputs.push({
                    accept: inp.accept || '',
                    display: window.getComputedStyle(inp).display,
                    parent: inp.parentElement ? inp.parentElement.tagName : 'none',
                    parentClasses: inp.parentElement ? (inp.parentElement.className || '').toString().substring(0, 40) : '',
                });
            }
        }
        return inputs;
    }""")
    print(f"\n  All file inputs: {len(all_file_inputs)}", flush=True)
    for fi in all_file_inputs:
        print(f"    accept={fi['accept']} display={fi['display']} parent={fi['parent']}.{fi['parentClasses']}", flush=True)

    # If file inputs found, try set_input_files
    if all_file_inputs:
        print("\n  Found file input! Trying set_input_files...", flush=True)
        try:
            page.locator('input[type="file"]').first.set_input_files(str(TEST_IMAGE))
            page.wait_for_timeout(5000)
            ss(page, "P43_02_file_set")
            print("  FILE SET SUCCESS!", flush=True)
        except Exception as e:
            print(f"  Failed: {e}", flush=True)

    # ============================================================
    #  ALTERNATIVE: SELECT CANVAS IMAGE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  SELECT CANVAS IMAGE AS REFERENCE", flush=True)
    print("=" * 60, flush=True)

    # Click one of the canvas thumbnails in the dialog
    canvas_imgs = page.evaluate("""() => {
        var items = [];
        for (const img of document.querySelectorAll('img')) {
            var r = img.getBoundingClientRect();
            var src = img.src || '';
            if (r.x > 200 && r.y > 200 && r.y < 500 && r.width > 30 && r.height > 30
                && (src.includes('blob:') || src.includes('dzine.ai') || src.includes('data:'))) {
                items.push({
                    src: src.substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cursor: window.getComputedStyle(img).cursor,
                    parentCursor: window.getComputedStyle(img.parentElement).cursor,
                });
            }
        }
        return items;
    }""")
    print(f"\n  Canvas images ({len(canvas_imgs)}):", flush=True)
    for img in canvas_imgs:
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} cursor={img['cursor']} pcur={img['parentCursor']} src={img['src'][:60]}", flush=True)

    if canvas_imgs:
        img = canvas_imgs[0]
        cx = img['x'] + img['w'] // 2
        cy = img['y'] + img['h'] // 2
        print(f"\n  Clicking canvas image at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(3000)

        ss(page, "P43_03_canvas_ref")

        # Check result — did dialog close? Did reference appear in CC panel?
        result = page.evaluate("""() => {
            var dialogOpen = false;
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Pick Image') && text.includes('Drop or select')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 200) { dialogOpen = true; break; }
                }
            }
            // Check for reference image in CC panel
            var ref = null;
            for (const img of document.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.x > 60 && r.x < 250 && r.y > 550 && r.y < 700
                    && r.width > 30) {
                    ref = {
                        src: (img.src || '').substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                    break;
                }
            }
            return {dialogOpen: dialogOpen, ref: ref};
        }""")
        print(f"  Dialog open: {result['dialogOpen']}", flush=True)
        print(f"  Reference image: {result['ref']}", flush=True)

        if result['ref']:
            print(f"  *** CANVAS IMAGE SELECTED AS REFERENCE! ***", flush=True)

    ss(page, "P43_04_final")
    print(f"\n\n===== PHASE 43 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
