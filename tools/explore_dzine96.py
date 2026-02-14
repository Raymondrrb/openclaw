"""Phase 96: Reliable tool opening via text match + Lip Sync & Img2Img.
Uses .tool-group text matching instead of y-coordinates.
A) Lip Sync: proper open → Pick Face → Next → crop → Next → audio/ready
B) Img2Img: proper open → model dropdown → map models
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


def open_tool(page, tool_name):
    """Open a tool by its label text, with toggle technique."""
    # First close any open panel
    page.evaluate("""() => {
        var c = document.querySelector('.c-gen-config.show .ico-close');
        if (c) c.click();
        var c2 = document.querySelector('.panels.show .ico-close');
        if (c2) c2.click();
    }""")
    page.wait_for_timeout(500)

    # Click the target tool by matching text
    result = page.evaluate("""(name) => {
        var groups = document.querySelectorAll('.tool-group');
        for (var g of groups) {
            var text = (g.innerText || '').trim();
            if (text.includes(name)) {
                g.click();
                var r = g.getBoundingClientRect();
                return 'clicked ' + name + ' at (' + Math.round(r.x) + ',' + Math.round(r.y) + ')';
            }
        }
        return name + ' not found in toolbar';
    }""", tool_name)
    print(f"  open_tool: {result}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    return result


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

    # First, map the toolbar to confirm positions
    toolbar = page.evaluate("""() => {
        var items = [];
        for (var g of document.querySelectorAll('.tool-group')) {
            var r = g.getBoundingClientRect();
            items.push({
                text: (g.innerText || '').trim().replace(/\\n/g, ' '),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }
        return items;
    }""")
    print("\n  Toolbar:", flush=True)
    for t in toolbar:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}'", flush=True)

    # ============================================================
    #  PART A: LIP SYNC COMPLETE FLOW
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART A: LIP SYNC", flush=True)
    print("=" * 60, flush=True)

    open_tool(page, "Lip Sync")

    # Verify Lip Sync panel is showing
    ls_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        var title = p.querySelector('.gen-config-header');
        return title ? (title.innerText || '').trim() : 'no title';
    }""")
    print(f"  Panel title: {ls_panel}", flush=True)

    if ls_panel and 'Lip Sync' in str(ls_panel):
        # Check for face picker buttons on canvas
        face_btns = page.evaluate("""() => {
            var items = [];
            for (var btn of document.querySelectorAll('button.pick-image')) {
                var r = btn.getBoundingClientRect();
                items.push({
                    text: (btn.innerText || '').trim(),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (btn.className || '').toString(),
                });
            }
            return items;
        }""")
        print(f"  Face buttons: {face_btns}", flush=True)

        # Click "Pick a Face Image"
        pick_result = page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button.pick-image')) {
                var text = (btn.innerText || '').trim();
                if (text.includes('Face Image') && !text.includes('Video')) {
                    btn.click();
                    return 'clicked: ' + text;
                }
            }
            return 'not found';
        }""")
        print(f"  Pick face: {pick_result}", flush=True)
        page.wait_for_timeout(3000)
        ss(page, "P96_01_after_pick_face")

        # Check for face picker dialog
        dialog_check = page.evaluate("""() => {
            var d = document.querySelector('.edit-image-dialog');
            if (d) {
                var r = d.getBoundingClientRect();
                return {
                    found: true,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
            }
            // Also check high z
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 900 && r.width > 400 && r.height > 300) {
                    return {
                        found: true, z: z,
                        text: (el.innerText || '').trim().substring(0, 100),
                    };
                }
            }
            return {found: false};
        }""")
        print(f"  Dialog: {dialog_check}", flush=True)

        if dialog_check.get('found'):
            # Wait for face detection
            page.wait_for_timeout(2000)

            # Check face count
            face_count = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('face selected')) return text;
                }
                return 'no face status found';
            }""")
            print(f"  Face: {face_count}", flush=True)
            ss(page, "P96_02_face_detected")

            # Step 1: Click Next (face → crop)
            print("\n  === NEXT 1 (face → crop) ===", flush=True)
            page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button')) {
                    var r = btn.getBoundingClientRect();
                    if ((btn.innerText || '').trim() === 'Next' && r.width > 0 && r.y > 600) {
                        btn.click(); return;
                    }
                }
            }""")
            page.wait_for_timeout(2000)
            ss(page, "P96_03_crop")

            # Step 2: Click Next (crop → next step)
            print("  === NEXT 2 (crop → ?) ===", flush=True)
            page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button')) {
                    var r = btn.getBoundingClientRect();
                    if ((btn.innerText || '').trim() === 'Next' && r.width > 0 && r.y > 600) {
                        btn.click(); return;
                    }
                }
            }""")
            page.wait_for_timeout(3000)
            ss(page, "P96_04_after_crop")

            # Check state — is there another dialog or did we return to panel?
            state = page.evaluate("""() => {
                // Check for dialog
                var dialog = null;
                for (var el of document.querySelectorAll('*')) {
                    var cs = window.getComputedStyle(el);
                    var z = parseInt(cs.zIndex) || 0;
                    var r = el.getBoundingClientRect();
                    if (z > 900 && r.width > 400 && r.height > 300) {
                        dialog = {
                            z: z,
                            text: (el.innerText || '').trim().substring(0, 200),
                            classes: (el.className || '').toString().substring(0, 60),
                        };
                        break;
                    }
                }

                // Check Lip Sync panel
                var panel = document.querySelector('.c-gen-config.show');
                var panelText = panel ? (panel.innerText || '').trim().substring(0, 400) : null;

                // Check for face preview image in panel
                var facePreview = null;
                if (panel) {
                    for (var img of panel.querySelectorAll('img')) {
                        var r = img.getBoundingClientRect();
                        if (r.width > 30 && r.height > 30 && r.y < 400) {
                            facePreview = {
                                src: (img.src || '').substring(0, 100),
                                w: Math.round(r.width), h: Math.round(r.height),
                            };
                        }
                    }
                }

                // Check canvas for audio upload elements
                var audioOnCanvas = [];
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    var cls = (el.className || '').toString();
                    if (r.x > 350 && r.x < 1050 && r.width > 30 && r.height > 15
                        && r.y > 50 && r.y < 850
                        && (cls.includes('audio') || cls.includes('voice')
                            || cls.includes('upload') || cls.includes('record')
                            || text.includes('audio') || text.includes('Audio')
                            || text.includes('Upload') || text.includes('Record')
                            || text.includes('TTS') || text.includes('voice')
                            || text.includes('mp3') || text.includes('wav'))) {
                        audioOnCanvas.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            text: text.substring(0, 50),
                            classes: cls.substring(0, 40),
                        });
                    }
                }

                return {dialog: dialog, panelText: panelText, facePreview: facePreview,
                        audioOnCanvas: audioOnCanvas};
            }""")

            print(f"\n  State after crop:", flush=True)
            if state.get('dialog'):
                print(f"  [DIALOG] z={state['dialog']['z']} c='{state['dialog']['classes'][:40]}'", flush=True)
                print(f"    text: {state['dialog']['text'][:150]}", flush=True)
            if state.get('panelText'):
                print(f"  [PANEL] {state['panelText'][:150]}", flush=True)
            if state.get('facePreview'):
                print(f"  [FACE PREVIEW] {state['facePreview']}", flush=True)
            print(f"  Audio on canvas: {state.get('audioOnCanvas', [])}", flush=True)

            # If there's still a "Pick a Face Image" on canvas, face wasn't set
            still_picking = page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button.pick-image')) {
                    var r = btn.getBoundingClientRect();
                    if (r.width > 0 && r.y > 0) return true;
                }
                return false;
            }""")
            print(f"  Still showing pick buttons: {still_picking}", flush=True)

            # If dialog still open, try clicking through more
            if state.get('dialog'):
                print("\n  Dialog still open — clicking Next/Confirm...", flush=True)
                page.evaluate("""() => {
                    for (var btn of document.querySelectorAll('button')) {
                        var text = (btn.innerText || '').trim();
                        var r = btn.getBoundingClientRect();
                        if ((text === 'Next' || text === 'Confirm' || text === 'Done')
                            && r.width > 0 && r.y > 600) {
                            btn.click(); return;
                        }
                    }
                }""")
                page.wait_for_timeout(3000)
                ss(page, "P96_05_final_dialog")

            # Full scan of the Lip Sync panel to see if audio upload appeared
            final_panel = page.evaluate("""() => {
                var p = document.querySelector('.c-gen-config.show');
                if (!p) return null;
                var items = [];
                var seen = new Set();
                for (var child of p.querySelectorAll('*')) {
                    var r = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    if (r.width > 0 && r.height > 0 && r.height < 80
                        && text.length > 0 && text.length < 60
                        && text.indexOf('\\n') === -1) {
                        var key = text + '|' + Math.round(r.y);
                        if (!seen.has(key)) {
                            seen.add(key);
                            items.push({
                                y: Math.round(r.y), text: text,
                                tag: child.tagName,
                            });
                        }
                    }
                }
                items.sort(function(a,b) { return a.y - b.y; });
                return items;
            }""")
            print(f"\n  Final panel elements ({len(final_panel) if final_panel else 0}):", flush=True)
            if final_panel:
                for item in final_panel[:25]:
                    print(f"    y={item['y']} <{item['tag']}> '{item['text']}'", flush=True)

    # ============================================================
    #  PART B: IMG2IMG MODEL DROPDOWN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART B: IMG2IMG", flush=True)
    print("=" * 60, flush=True)

    open_tool(page, "Img2Img")

    # Verify
    i2i_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show.img2img-config-panel');
        if (p) return 'img2img panel open';
        var p2 = document.querySelector('.c-gen-config.show');
        if (p2) {
            var h = p2.querySelector('.gen-config-header');
            return h ? (h.innerText || '').trim() : 'unknown panel';
        }
        return 'no panel';
    }""")
    print(f"  Panel: {i2i_panel}", flush=True)

    if 'img2img' in str(i2i_panel).lower() or 'Image-to-Image' in str(i2i_panel):
        # Click the model/style area to open dropdown
        print("\n  Clicking model selector...", flush=True)
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var style = panel.querySelector('.c-style');
            if (style) style.click();
        }""")
        page.wait_for_timeout(2000)
        ss(page, "P96_06_model_click")

        # Check for dropdown/panel
        model_dropdown = page.evaluate("""() => {
            // Check style-list-panel
            var slp = document.querySelector('.style-list-panel');
            if (slp) {
                var r = slp.getBoundingClientRect();
                var items = [];
                for (var child of slp.querySelectorAll('.style-item, [class*="model-item"], [class*="option"]')) {
                    var text = (child.innerText || '').trim();
                    var cr = child.getBoundingClientRect();
                    if (text.length > 2 && cr.width > 0) {
                        items.push(text.substring(0, 40));
                    }
                }
                return {
                    type: 'style-list-panel',
                    w: Math.round(r.width), h: Math.round(r.height),
                    items: [...new Set(items)],
                };
            }

            // Check for any new overlay/dropdown
            var newPanels = [];
            for (var el of document.querySelectorAll('*')) {
                var cls = (el.className || '').toString();
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.x > 50 && r.x < 500
                    && (cls.includes('list') || cls.includes('dropdown')
                        || cls.includes('select') || cls.includes('model'))) {
                    newPanels.push({
                        classes: cls.substring(0, 50),
                        w: Math.round(r.width), h: Math.round(r.height),
                        x: Math.round(r.x), y: Math.round(r.y),
                    });
                }
            }
            return {type: 'search', panels: newPanels};
        }""")
        print(f"  Model dropdown: {model_dropdown}", flush=True)

        # If style-list-panel exists but width=0, force it open and read
        if model_dropdown.get('type') == 'style-list-panel' and model_dropdown.get('w', 0) == 0:
            print("  Panel has width 0 — forcing visible...", flush=True)
            models = page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (!slp) return null;
                slp.style.cssText = 'width:350px !important; display:block !important; visibility:visible !important; overflow:auto !important; position:absolute !important; z-index:9999 !important; left:80px !important; top:50px !important; background:#1a1a1a !important; max-height:800px !important;';

                var items = [];
                var seen = new Set();
                for (var child of slp.querySelectorAll('*')) {
                    var text = (child.innerText || '').trim();
                    var cls = (child.className || '').toString();
                    if (text.length > 3 && text.length < 50
                        && text.indexOf('\\n') === -1
                        && !seen.has(text)) {
                        seen.add(text);
                        items.push({
                            text: text,
                            classes: cls.substring(0, 40),
                            tag: child.tagName,
                        });
                    }
                }
                return items;
            }""")
            print(f"\n  Forced models ({len(models) if models else 0}):", flush=True)
            if models:
                for m in models[:50]:
                    print(f"    <{m['tag']}> c='{m['classes'][:25]}' '{m['text']}'", flush=True)
            ss(page, "P96_07_forced_models")

            # Reset
            page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (slp) slp.removeAttribute('style');
            }""")

        elif model_dropdown.get('items'):
            print(f"\n  Models ({len(model_dropdown['items'])}):", flush=True)
            for m in model_dropdown['items']:
                print(f"    {m}", flush=True)

    ss(page, "P96_08_final")

    print(f"\n\n===== PHASE 96 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
