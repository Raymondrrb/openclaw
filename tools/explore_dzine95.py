"""Phase 95: Complete Lip Sync face selection + Img2Img model dropdown.
A) Lip Sync: click Pick a Face Image → face detect → Next → crop → Next →
   see what panel shows (audio upload or ready to generate?)
B) Img2Img: click model name to open dropdown, map all available models
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
    #  PART A: LIP SYNC — COMPLETE FACE SELECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART A: LIP SYNC COMPLETE FLOW", flush=True)
    print("=" * 60, flush=True)

    # A1: Open Lip Sync
    print("  A1: Opening Lip Sync...", flush=True)
    page.mouse.click(37, 750)  # distant tool
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.evaluate("""() => {
        var c = document.querySelector('.panels.show .ico-close');
        if (c) c.click();
    }""")
    page.wait_for_timeout(500)
    page.mouse.click(37, 400)  # Lip Sync
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # A2: Click "Pick a Face Image" on the canvas
    print("  A2: Clicking 'Pick a Face Image'...", flush=True)
    pick_result = page.evaluate("""() => {
        var btn = document.querySelector('button.pick-image:not(.pick-video)');
        if (btn) {
            var r = btn.getBoundingClientRect();
            if (r.width > 0) {
                btn.click();
                return 'clicked pick-image at (' + Math.round(r.x) + ',' + Math.round(r.y) + ')';
            }
        }
        return 'button not found';
    }""")
    print(f"  {pick_result}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # A3: Check what opened — should be a picker dialog
    print("  A3: Checking what opened...", flush=True)
    ss(page, "P95_01_after_pick_face")

    # Look for any new dialog or overlay
    overlay_check = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 200 && r.height > 100) {
                items.push({
                    z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 150),
                });
            }
        }
        return items;
    }""")
    print(f"  Overlays ({len(overlay_check)}):", flush=True)
    for o in overlay_check:
        print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']} c='{o['classes'][:40]}' '{o['text'][:60]}'", flush=True)

    # Check if "Pick a Face" dialog appeared (class edit-image-dialog from P93)
    face_dialog = page.evaluate("""() => {
        var d = document.querySelector('.edit-image-dialog');
        if (d) {
            var r = d.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    }""")
    print(f"  Face dialog (.edit-image-dialog): {face_dialog}", flush=True)

    # If we have the face dialog, navigate it
    if face_dialog or any(o.get('z', 0) > 900 for o in overlay_check):
        # Look for faces and the image
        print("\n  A4: Face dialog found — navigating...", flush=True)

        # Wait a bit for face detection
        page.wait_for_timeout(2000)

        # Check for face count text
        face_count = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('face selected')) return text;
            }
            return null;
        }""")
        print(f"  Face count: {face_count}", flush=True)
        ss(page, "P95_02_face_detected")

        # Click Next (face detection → crop)
        print("  Clicking Next (face → crop)...", flush=True)
        n1 = page.evaluate("""() => {
            var btns = document.querySelectorAll('button');
            for (var btn of btns) {
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (text === 'Next' && r.width > 0 && r.y > 600) {
                    btn.click();
                    return 'clicked Next at y=' + Math.round(r.y);
                }
            }
            return 'not found';
        }""")
        print(f"  Next 1: {n1}", flush=True)
        page.wait_for_timeout(2000)
        ss(page, "P95_03_crop_step")

        # Check for crop step elements
        crop_check = page.evaluate("""() => {
            var items = [];
            for (var btn of document.querySelectorAll('button.ratio-item, .ratio-item')) {
                var r = btn.getBoundingClientRect();
                var text = (btn.innerText || '').trim();
                if (r.width > 0) {
                    items.push({
                        text: text, x: Math.round(r.x), y: Math.round(r.y),
                        selected: btn.classList.contains('selected'),
                    });
                }
            }
            return items;
        }""")
        print(f"  Crop ratios: {crop_check}", flush=True)

        # Click Next (crop → next step)
        print("  Clicking Next (crop → next)...", flush=True)
        n2 = page.evaluate("""() => {
            var btns = document.querySelectorAll('button');
            for (var btn of btns) {
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (text === 'Next' && r.width > 0 && r.y > 600) {
                    btn.click();
                    return 'clicked Next at y=' + Math.round(r.y);
                }
            }
            return 'not found';
        }""")
        print(f"  Next 2: {n2}", flush=True)
        page.wait_for_timeout(3000)
        close_dialogs(page)

        # A5: Check what we have now
        print("\n  A5: State after crop Next...", flush=True)
        ss(page, "P95_04_after_crop_next")

        # Check for another dialog step
        dialog_after = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 500 && r.width > 300 && r.height > 200) {
                    return {
                        z: z, classes: (el.className || '').toString().substring(0, 60),
                        text: (el.innerText || '').trim().substring(0, 200),
                    };
                }
            }
            return null;
        }""")
        print(f"  Dialog after: {dialog_after}", flush=True)

        # Check panel state
        panel_now = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return null;
            var text = (p.innerText || '').trim();
            // Check for images in panel
            var imgs = [];
            for (var img of p.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.width > 20 && r.height > 20) {
                    imgs.push({
                        src: (img.src || '').substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            // Check for audio upload area
            var audioEls = [];
            for (var el of p.querySelectorAll('*')) {
                var cls = (el.className || '').toString();
                if (cls.includes('audio') || cls.includes('voice') || cls.includes('upload')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        audioEls.push({
                            classes: cls.substring(0, 40),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width),
                            text: (el.innerText || '').trim().substring(0, 40),
                        });
                    }
                }
            }
            return {
                text: text.substring(0, 300),
                hasWarning: text.includes('Please pick'),
                imgs: imgs,
                audioEls: audioEls,
            };
        }""")
        print(f"\n  Panel state:", flush=True)
        if panel_now:
            print(f"    Warning present: {panel_now.get('hasWarning')}", flush=True)
            print(f"    Text: {panel_now.get('text', '')[:200]}", flush=True)
            print(f"    Images: {panel_now.get('imgs', [])}", flush=True)
            print(f"    Audio elements: {panel_now.get('audioEls', [])}", flush=True)

        # Check canvas area for changes
        canvas_now = page.evaluate("""() => {
            var items = [];
            var seen = new Set();
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                var cls = (el.className || '').toString();
                if (r.x > 350 && r.x < 1050 && r.y > 50 && r.y < 850
                    && r.width > 30 && r.height > 15
                    && text.length > 0 && text.length < 80
                    && text.indexOf('\\n') === -1
                    && r.height < 100) {
                    var key = text.substring(0,20) + '|' + Math.round(r.y / 10);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            text: text.substring(0, 60),
                            tag: el.tagName,
                            classes: cls.substring(0, 40),
                        });
                    }
                }
            }
            items.sort(function(a,b) { return a.y - b.y; });
            return items.slice(0, 15);
        }""")
        print(f"\n  Canvas elements ({len(canvas_now)}):", flush=True)
        for c in canvas_now:
            print(f"    ({c['x']},{c['y']}) '{c['text'][:45]}' <{c['tag']}> c='{c['classes'][:25]}'", flush=True)

    else:
        print("  No face dialog found — checking alternatives...", flush=True)
        # Maybe it opened a file picker or local upload dialog
        # Try clicking Upload a Face Video as well
        page.evaluate("""() => {
            var btn = document.querySelector('button.pick-image.pick-video');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(2000)
        ss(page, "P95_02b_upload_video")

    # ============================================================
    #  PART B: IMG2IMG MODEL DROPDOWN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART B: IMG2IMG MODEL DROPDOWN", flush=True)
    print("=" * 60, flush=True)

    # Close everything
    for _ in range(5):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.evaluate("""() => {
        var c = document.querySelector('.c-gen-config.show .ico-close');
        if (c) c.click();
    }""")
    page.wait_for_timeout(1000)

    # Open Img2Img
    page.mouse.click(37, 750)  # Storyboard
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.evaluate("""() => {
        var c = document.querySelector('.panels.show .ico-close') ||
                document.querySelector('.c-gen-config.show .ico-close');
        if (c) c.click();
    }""")
    page.wait_for_timeout(500)

    # Click Img2Img by label
    i2i_opened = page.evaluate("""() => {
        for (var el of document.querySelectorAll('.tool-group')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Img2Img')) {
                el.click();
                return 'clicked';
            }
        }
        return 'not found';
    }""")
    print(f"  Img2Img: {i2i_opened}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Verify panel
    panel_check = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show.img2img-config-panel');
        return p ? 'Img2Img panel open' : 'not open';
    }""")
    print(f"  Panel: {panel_check}", flush=True)

    if panel_check == 'Img2Img panel open':
        # B1: Click the model name to open dropdown
        print("\n  B1: Clicking model selector...", flush=True)
        model_clicked = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'no panel';
            // Click .c-style which contains the model name
            var style = panel.querySelector('.c-style');
            if (style) {
                style.click();
                var r = style.getBoundingClientRect();
                return 'clicked .c-style at (' + Math.round(r.x) + ',' + Math.round(r.y) + ')';
            }
            // Try .style-name
            var sn = panel.querySelector('.style-name');
            if (sn) {
                sn.click();
                return 'clicked .style-name';
            }
            return 'no model element';
        }""")
        print(f"  Model click: {model_clicked}", flush=True)
        page.wait_for_timeout(2000)
        ss(page, "P95_05_model_dropdown")

        # B2: Map the model dropdown
        print("  B2: Mapping model dropdown...", flush=True)
        dropdown = page.evaluate("""() => {
            // Check for style-list-panel or model dropdown
            var items = [];
            var candidates = [
                '.style-list-panel', '.model-list', '.option-list',
                '[class*="dropdown"]', '[class*="model-select"]',
                '.style-select-panel',
            ];
            for (var sel of candidates) {
                var el = document.querySelector(sel);
                if (el) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        items.push({
                            selector: sel,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    }
                }
            }

            // Check for high-z overlays that might be the dropdown
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 100 && r.width > 150 && r.height > 200 && r.x > 50 && r.x < 400) {
                    var modelNames = [];
                    for (var child of el.querySelectorAll('*')) {
                        var text = (child.innerText || '').trim();
                        var cr = child.getBoundingClientRect();
                        if (text.length > 3 && text.length < 40 && cr.height < 30
                            && cr.height > 8 && cr.width > 50
                            && text.indexOf('\\n') === -1) {
                            modelNames.push(text);
                        }
                    }
                    // Dedupe
                    modelNames = [...new Set(modelNames)];
                    if (modelNames.length > 2) {
                        items.push({
                            selector: 'z=' + z,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            models: modelNames.slice(0, 30),
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"\n  Dropdown containers ({len(dropdown)}):", flush=True)
        for d in dropdown:
            print(f"    {d['selector']} ({d['x']},{d['y']}) {d['w']}x{d['h']}", flush=True)
            if d.get('models'):
                print(f"    Models: {d['models']}", flush=True)

        # Also check if style-list-panel exists but has width=0 (known issue)
        style_panel = page.evaluate("""() => {
            var slp = document.querySelector('.style-list-panel');
            if (!slp) return null;
            var r = slp.getBoundingClientRect();
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                display: window.getComputedStyle(slp).display,
                visibility: window.getComputedStyle(slp).visibility,
                overflow: window.getComputedStyle(slp).overflow,
                childCount: slp.children.length,
            };
        }""")
        print(f"\n  .style-list-panel: {style_panel}", flush=True)

        # If style-list-panel exists with width=0, try forcing it visible
        if style_panel and style_panel.get('w', 0) == 0:
            print("  Trying to force style panel visible...", flush=True)
            page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (slp) {
                    slp.style.width = '300px';
                    slp.style.display = 'block';
                    slp.style.visibility = 'visible';
                    slp.style.overflow = 'auto';
                    slp.style.position = 'absolute';
                    slp.style.zIndex = '999';
                    slp.style.left = '80px';
                    slp.style.top = '50px';
                    slp.style.background = '#1a1a1a';
                }
            }""")
            page.wait_for_timeout(1000)
            ss(page, "P95_06_forced_style_panel")

            # Read model names from the forced panel
            forced_models = page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (!slp) return null;
                var r = slp.getBoundingClientRect();
                var items = [];
                for (var child of slp.querySelectorAll('*')) {
                    var text = (child.innerText || '').trim();
                    var cr = child.getBoundingClientRect();
                    if (text.length > 2 && text.length < 50 && cr.height > 5 && cr.height < 40
                        && cr.width > 20 && text.indexOf('\\n') === -1) {
                        items.push(text);
                    }
                }
                return {
                    w: Math.round(r.width), h: Math.round(r.height),
                    items: [...new Set(items)].slice(0, 50),
                };
            }""")
            print(f"\n  Forced panel: {forced_models}", flush=True)

            # Reset the panel
            page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (slp) slp.removeAttribute('style');
            }""")

    ss(page, "P95_07_final")

    print(f"\n\n===== PHASE 95 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
