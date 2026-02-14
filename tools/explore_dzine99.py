"""Phase 99: Lip Sync COMPLETE — Pick Image → Pick Face → Crop → Audio/Ready.
Plus: Img2Img model dropdown after clean close.
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


def dismiss_popups(page):
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Skip' && el.getBoundingClientRect().width > 20) {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)


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


def click_next(page):
    """Click Next button anywhere on page."""
    coords = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Next' && r.width > 30 && r.height > 15 && r.y > 500) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if coords:
        page.mouse.click(coords['x'], coords['y'])
        return True
    return False


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
    #  PART A: LIP SYNC — FULL FLOW
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART A: LIP SYNC COMPLETE", flush=True)
    print("=" * 60, flush=True)

    # A1: Open Lip Sync
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    print("  A1: Lip Sync opened", flush=True)

    # A2: Click "Pick a Face Image"
    page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button.pick-image')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Face Image') && !text.includes('Video')) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)
    print("  A2: Clicked Pick a Face Image", flush=True)

    # A3: "Pick Image" dialog — map and click first canvas layer
    pick_dialog = page.evaluate("""() => {
        // Find the Pick Image dialog
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 300 && r.height > 200) {
                // Find canvas layer thumbnails
                var thumbnails = [];
                for (var img of el.querySelectorAll('img')) {
                    var ir = img.getBoundingClientRect();
                    if (ir.width > 50 && ir.height > 50 && ir.y > 300) {
                        thumbnails.push({
                            src: (img.src || '').substring(0, 100),
                            x: Math.round(ir.x + ir.width/2),
                            y: Math.round(ir.y + ir.height/2),
                            w: Math.round(ir.width),
                            h: Math.round(ir.height),
                        });
                    }
                }
                // Title
                var title = '';
                for (var h of el.querySelectorAll('*')) {
                    var t = (h.innerText || '').trim();
                    if (t === 'Pick Image' || t === 'Pick a Face') {
                        title = t; break;
                    }
                }
                return {
                    title: title,
                    z: z,
                    thumbnails: thumbnails,
                };
            }
        }
        return null;
    }""")
    print(f"  A3: Pick dialog: title={pick_dialog.get('title') if pick_dialog else 'None'}, "
          f"thumbs={len(pick_dialog.get('thumbnails', [])) if pick_dialog else 0}", flush=True)

    if pick_dialog and pick_dialog.get('thumbnails'):
        # Click the first canvas thumbnail
        first = pick_dialog['thumbnails'][0]
        print(f"  Clicking first thumbnail at ({first['x']},{first['y']}) {first['w']}x{first['h']}", flush=True)
        page.mouse.click(first['x'], first['y'])
        page.wait_for_timeout(4000)
        close_dialogs(page)
        ss(page, "P99_01_after_thumb_click")

        # A4: Should now be "Pick a Face" dialog with face detection
        face_check = page.evaluate("""() => {
            // Check for face selected text
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t.includes('face selected')) return t;
            }
            // Check for "Mark Face Manually"
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t === 'Mark Face Manually') return 'face detection dialog found';
            }
            // Check for "How Cropping Works" (already on crop step?)
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t === 'How Cropping Works') return 'already on crop step';
            }
            return null;
        }""")
        print(f"  A4: Face check: {face_check}", flush=True)

        if face_check:
            if 'crop' not in str(face_check).lower():
                # On face detection step — click Next
                print("  === NEXT 1: Face → Crop ===", flush=True)
                if click_next(page):
                    page.wait_for_timeout(2000)
                    ss(page, "P99_02_crop")
                    print("  On crop step", flush=True)

            # Now on crop step — click Next
            print("  === NEXT 2: Crop → ? ===", flush=True)
            if click_next(page):
                page.wait_for_timeout(4000)
                close_dialogs(page)
                ss(page, "P99_03_after_crop")

                # A5: MAP EVERYTHING — this is the critical state
                print("\n  === A5: CRITICAL STATE CHECK ===", flush=True)

                state = page.evaluate("""() => {
                    var result = {};

                    // 1. Any dialog still open?
                    result.dialogOpen = false;
                    for (var el of document.querySelectorAll('*')) {
                        var cs = window.getComputedStyle(el);
                        var z = parseInt(cs.zIndex) || 0;
                        var r = el.getBoundingClientRect();
                        if (z > 500 && r.width > 300 && r.height > 200 && r.y > 0) {
                            result.dialogOpen = true;
                            result.dialogText = (el.innerText || '').trim().substring(0, 300);
                            break;
                        }
                    }

                    // 2. Panel content
                    var p = document.querySelector('.c-gen-config.show');
                    if (p) {
                        result.panelHTML = p.innerHTML.substring(0, 500);
                        result.panelText = (p.innerText || '').trim().substring(0, 400);
                        // Face preview?
                        var faceImgs = [];
                        for (var img of p.querySelectorAll('img')) {
                            var ir = img.getBoundingClientRect();
                            if (ir.width > 30 && ir.height > 30) {
                                faceImgs.push({
                                    src: (img.src || '').substring(0, 100),
                                    w: Math.round(ir.width), h: Math.round(ir.height),
                                    y: Math.round(ir.y),
                                });
                            }
                        }
                        result.panelImages = faceImgs;
                    }

                    // 3. Canvas center content
                    var canvasEls = [];
                    var seen = new Set();
                    for (var el of document.querySelectorAll('button, [class*="upload"], [class*="audio"], [class*="voice"]')) {
                        var r = el.getBoundingClientRect();
                        var text = (el.innerText || '').trim();
                        if (r.x > 300 && r.x < 1100 && r.y > 50 && r.y < 850
                            && r.width > 30 && text.length > 0 && text.length < 80) {
                            var key = text.substring(0,20) + '|' + Math.round(r.y/10);
                            if (!seen.has(key)) {
                                seen.add(key);
                                canvasEls.push({
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    text: text.substring(0, 60),
                                    tag: el.tagName,
                                    classes: (el.className || '').toString().substring(0, 40),
                                });
                            }
                        }
                    }
                    canvasEls.sort(function(a,b){return a.y - b.y});
                    result.canvasButtons = canvasEls.slice(0, 20);

                    // 4. File inputs
                    result.fileInputs = [];
                    for (var inp of document.querySelectorAll('input[type="file"]')) {
                        result.fileInputs.push({
                            accept: inp.accept || 'any',
                            parent: (inp.parentElement?.className || '').substring(0, 40),
                        });
                    }

                    return result;
                }""")

                print(f"  Dialog open: {state.get('dialogOpen')}", flush=True)
                if state.get('dialogText'):
                    print(f"  Dialog text: {state['dialogText'][:150]}", flush=True)
                if state.get('panelText'):
                    has_warning = 'Please pick' in state['panelText']
                    print(f"  Panel (warning={has_warning}): {state['panelText'][:150]}", flush=True)
                if state.get('panelImages'):
                    print(f"  Panel images: {state['panelImages']}", flush=True)
                print(f"\n  Canvas buttons ({len(state.get('canvasButtons', []))}):", flush=True)
                for c in state.get('canvasButtons', []):
                    print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> '{c['text'][:45]}' c='{c['classes'][:25]}'", flush=True)
                print(f"  File inputs: {state.get('fileInputs', [])}", flush=True)

                # If there's a third dialog step, try clicking through
                if state.get('dialogOpen'):
                    print("\n  Dialog still open — trying Next/Confirm/Done...", flush=True)
                    page.evaluate("""() => {
                        for (var btn of document.querySelectorAll('button')) {
                            var text = (btn.innerText || '').trim();
                            var r = btn.getBoundingClientRect();
                            if ((text === 'Next' || text === 'Confirm' || text === 'Done' || text === 'OK')
                                && r.width > 30 && r.y > 500) {
                                btn.click(); return;
                            }
                        }
                    }""")
                    page.wait_for_timeout(3000)
                    ss(page, "P99_04_third_next")

                    # Check state again
                    final = page.evaluate("""() => {
                        var p = document.querySelector('.c-gen-config.show');
                        return p ? (p.innerText || '').trim().substring(0, 300) : null;
                    }""")
                    print(f"  Panel after third click: {final[:200] if final else 'None'}", flush=True)

    # ============================================================
    #  PART B: IMG2IMG — FRESH PAGE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART B: IMG2IMG (fresh page)", flush=True)
    print("=" * 60, flush=True)

    # Close everything and reload
    page.close()
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    wait_for_canvas(page)
    close_dialogs(page)

    # Open Img2Img directly
    print("  Opening Img2Img...", flush=True)
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Check panel
    panel_check = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        return (p.className || '').toString();
    }""")
    print(f"  Panel class: {panel_check}", flush=True)
    ss(page, "P99_05_img2img")

    if panel_check and 'img2img' in panel_check:
        # Click model area
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var style = panel?.querySelector('.c-style');
            if (style) style.click();
        }""")
        page.wait_for_timeout(2000)

        # Check what happened
        slp = page.evaluate("""() => {
            var slp = document.querySelector('.style-list-panel');
            if (!slp) return {exists: false};
            var r = slp.getBoundingClientRect();
            return {
                exists: true,
                w: Math.round(r.width), h: Math.round(r.height),
                innerHTML_len: slp.innerHTML.length,
                childCount: slp.children.length,
            };
        }""")
        print(f"  style-list-panel: {slp}", flush=True)

        if slp.get('exists') and slp.get('innerHTML_len', 0) > 100:
            # Force visible and read
            models = page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (!slp) return null;
                slp.style.cssText = 'width:350px !important; height:800px !important; display:block !important; visibility:visible !important; overflow-y:auto !important; position:absolute !important; z-index:9999 !important; left:80px !important; top:50px !important; background:#1a1a1a !important;';

                var items = [];
                var seen = new Set();
                // Try multiple selectors for model names
                var nameEls = slp.querySelectorAll('.style-name, .name, [class*="style-name"]');
                for (var el of nameEls) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 50 && !seen.has(text)) {
                        seen.add(text);
                        items.push(text);
                    }
                }
                // If few, try all text
                if (items.length < 5) {
                    for (var el of slp.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        var tag = el.tagName;
                        var r = el.getBoundingClientRect();
                        if (text.length > 3 && text.length < 40
                            && !text.includes('\\n') && !seen.has(text)
                            && r.height < 40 && r.height > 5) {
                            seen.add(text);
                            items.push(text);
                        }
                    }
                }
                return items.slice(0, 80);
            }""")
            page.wait_for_timeout(500)
            ss(page, "P99_06_forced_models")
            print(f"\n  Models ({len(models) if models else 0}):", flush=True)
            if models:
                for m in models:
                    print(f"    {m}", flush=True)

            # Reset
            page.evaluate("() => document.querySelector('.style-list-panel')?.removeAttribute('style')")

        # Also try clicking the style-name text directly (like Chat Editor .option-label approach)
        print("\n  Trying .style-name click approach...", flush=True)
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var sn = panel?.querySelector('.style-name');
            if (sn) sn.click();
        }""")
        page.wait_for_timeout(2000)
        ss(page, "P99_07_style_name_click")

        # Check for any new panel/dropdown
        new_panels = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 100 && r.width > 100 && r.height > 100 && r.x > 50 && r.x < 500
                    && r.y > 0) {
                    var texts = [];
                    var seen = new Set();
                    for (var child of el.querySelectorAll('*')) {
                        var t = (child.innerText || '').trim();
                        var cr = child.getBoundingClientRect();
                        if (t.length > 3 && t.length < 40 && cr.height < 30
                            && !seen.has(t) && t.indexOf('\\n') === -1) {
                            seen.add(t);
                            texts.push(t);
                        }
                    }
                    if (texts.length > 3) {
                        items.push({
                            z: z,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            texts: texts.slice(0, 20),
                            classes: (el.className || '').toString().substring(0, 50),
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"\n  New panels after style-name click ({len(new_panels)}):", flush=True)
        for p in new_panels:
            print(f"    z={p['z']} ({p['x']},{p['y']}) {p['w']}x{p['h']} c='{p['classes'][:35]}'", flush=True)
            print(f"    texts: {p['texts']}", flush=True)

    ss(page, "P99_08_final")
    print(f"\n\n===== PHASE 99 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
