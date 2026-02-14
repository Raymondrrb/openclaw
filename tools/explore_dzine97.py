"""Phase 97: Mouse-click based tool opening + Lip Sync + Img2Img.
Key fix: use page.mouse.click() instead of el.click() for toolbar.
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


def open_tool_by_mouse(page, tool_name):
    """Open a tool by finding its coords and using page.mouse.click()."""
    coords = page.evaluate("""(name) => {
        for (var g of document.querySelectorAll('.tool-group')) {
            var text = (g.innerText || '').trim();
            if (text.includes(name)) {
                var r = g.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""", tool_name)
    if not coords:
        print(f"  Tool '{tool_name}' not found", flush=True)
        return False

    # First click a different tool to ensure toggle works
    # Use the center of canvas to deselect
    page.mouse.click(700, 450)
    page.wait_for_timeout(300)

    # Click the tool
    page.mouse.click(coords['x'], coords['y'])
    print(f"  Clicked {tool_name} at ({coords['x']},{coords['y']})", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Verify panel opened
    panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (p) {
            var h = p.querySelector('.gen-config-header');
            return h ? (h.innerText || '').trim() : 'panel open (no header)';
        }
        var p2 = document.querySelector('.panels.show');
        if (p2) return 'panels.show';
        return null;
    }""")
    print(f"  Panel: {panel}", flush=True)
    return panel is not None


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
    #  PART A: LIP SYNC — FULL FACE SELECTION FLOW
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART A: LIP SYNC", flush=True)
    print("=" * 60, flush=True)

    # A1: Open Lip Sync
    opened = open_tool_by_mouse(page, "Lip Sync")
    if not opened:
        # Toggle: click a distant tool first, then Lip Sync
        print("  Retrying with toggle...", flush=True)
        page.mouse.click(40, 750)  # Storyboard area
        page.wait_for_timeout(2000)
        close_dialogs(page)
        # Close any opened panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        # Now click Lip Sync
        page.mouse.click(40, 420)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        dismiss_popups(page)

    # Verify Lip Sync is active
    ls_check = page.evaluate("""() => {
        // Check for lip-sync-config-panel
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) return 'lip-sync-config-panel found';
        // Check c-gen-config
        var p = document.querySelector('.c-gen-config.show');
        if (p) {
            var text = (p.innerText || '').trim();
            if (text.includes('Lip Sync')) return 'Lip Sync in panel';
            return 'other panel: ' + text.substring(0, 50);
        }
        return 'no panel';
    }""")
    print(f"  Lip Sync check: {ls_check}", flush=True)
    ss(page, "P97_01_lip_sync_panel")

    if 'Lip Sync' in str(ls_check):
        # A2: Click "Pick a Face Image" using mouse click
        pick_coords = page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button.pick-image')) {
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (text.includes('Face Image') && !text.includes('Video') && r.width > 0) {
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")
        print(f"  Pick face coords: {pick_coords}", flush=True)

        if pick_coords:
            page.mouse.click(pick_coords['x'], pick_coords['y'])
            print(f"  Clicked Pick a Face Image", flush=True)
            page.wait_for_timeout(4000)
            close_dialogs(page)
            ss(page, "P97_02_face_dialog")

            # Check for face detection dialog
            face_dialog = page.evaluate("""() => {
                var d = document.querySelector('.edit-image-dialog');
                if (d) {
                    var r = d.getBoundingClientRect();
                    // Look for face count
                    var faceText = '';
                    for (var el of d.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (t.includes('face selected')) {faceText = t; break;}
                    }
                    return {found: true, w: Math.round(r.width), h: Math.round(r.height),
                            faces: faceText};
                }
                return {found: false};
            }""")
            print(f"  Face dialog: {face_dialog}", flush=True)

            if face_dialog.get('found'):
                # Click Next (face → crop)
                print("\n  Clicking Next (face → crop)...", flush=True)
                next_coords = page.evaluate("""() => {
                    for (var btn of document.querySelectorAll('button')) {
                        var text = (btn.innerText || '').trim();
                        var r = btn.getBoundingClientRect();
                        if (text === 'Next' && r.width > 40 && r.y > 600) {
                            return {x: Math.round(r.x + r.width/2),
                                    y: Math.round(r.y + r.height/2)};
                        }
                    }
                    return null;
                }""")
                if next_coords:
                    page.mouse.click(next_coords['x'], next_coords['y'])
                    page.wait_for_timeout(2000)
                    ss(page, "P97_03_crop")

                    # Click Next (crop → audio/done)
                    print("  Clicking Next (crop → audio)...", flush=True)
                    next_coords2 = page.evaluate("""() => {
                        for (var btn of document.querySelectorAll('button')) {
                            var text = (btn.innerText || '').trim();
                            var r = btn.getBoundingClientRect();
                            if (text === 'Next' && r.width > 40 && r.y > 600) {
                                return {x: Math.round(r.x + r.width/2),
                                        y: Math.round(r.y + r.height/2)};
                            }
                        }
                        return null;
                    }""")
                    if next_coords2:
                        page.mouse.click(next_coords2['x'], next_coords2['y'])
                        page.wait_for_timeout(4000)
                        close_dialogs(page)
                        ss(page, "P97_04_after_all_next")

                        # Map final state
                        final_state = page.evaluate("""() => {
                            var result = {};

                            // Check for any dialog
                            result.hasDialog = false;
                            for (var el of document.querySelectorAll('*')) {
                                var cs = window.getComputedStyle(el);
                                var z = parseInt(cs.zIndex) || 0;
                                var r = el.getBoundingClientRect();
                                if (z > 900 && r.width > 300 && r.height > 200) {
                                    result.hasDialog = true;
                                    result.dialogText = (el.innerText || '').trim().substring(0, 200);
                                    break;
                                }
                            }

                            // Lip Sync panel full text
                            var p = document.querySelector('.c-gen-config.show');
                            result.panelText = p ? (p.innerText || '').trim().substring(0, 500) : null;

                            // Check for face preview in panel
                            if (p) {
                                var prevImgs = [];
                                for (var img of p.querySelectorAll('img')) {
                                    var r = img.getBoundingClientRect();
                                    if (r.width > 30 && r.height > 30 && r.y > 60 && r.y < 400) {
                                        prevImgs.push({
                                            src: (img.src || '').substring(0, 100),
                                            w: Math.round(r.width),
                                            h: Math.round(r.height),
                                            y: Math.round(r.y),
                                        });
                                    }
                                }
                                result.panelImgs = prevImgs;
                            }

                            // Check for audio upload area on canvas
                            var audioEls = [];
                            for (var el of document.querySelectorAll('*')) {
                                var r = el.getBoundingClientRect();
                                var cls = (el.className || '').toString();
                                var text = (el.innerText || '').trim();
                                if (r.x > 300 && r.x < 1100 && r.y > 50 && r.y < 850
                                    && r.width > 20 && r.height > 10) {
                                    if (cls.includes('audio') || cls.includes('voice')
                                        || cls.includes('record') || cls.includes('mic')
                                        || cls.includes('upload-audio')
                                        || text.includes('Audio') || text.includes('audio')
                                        || text.includes('Upload Audio')
                                        || text.includes('Record') || text.includes('TTS')
                                        || text.includes('voice') || text.includes('Voice')
                                        || text.includes('Browse') || text.includes('.mp3')
                                        || text.includes('.wav') || text.includes('Drag')) {
                                        audioEls.push({
                                            x: Math.round(r.x), y: Math.round(r.y),
                                            w: Math.round(r.width), h: Math.round(r.height),
                                            text: text.substring(0, 50),
                                            classes: cls.substring(0, 40),
                                        });
                                    }
                                }
                            }
                            result.audioElements = audioEls;

                            // Check canvas center for any new UI elements
                            var canvasEls = [];
                            var seen = new Set();
                            for (var el of document.querySelectorAll('*')) {
                                var r = el.getBoundingClientRect();
                                var text = (el.innerText || '').trim();
                                if (r.x > 350 && r.x < 1050 && r.y > 100 && r.y < 800
                                    && r.width > 50 && r.height > 20
                                    && text.length > 0 && text.length < 60
                                    && text.indexOf('\\n') === -1
                                    && r.height < 80) {
                                    var key = text.substring(0,20) + '|' + Math.round(r.y/10);
                                    if (!seen.has(key)) {
                                        seen.add(key);
                                        canvasEls.push({
                                            x: Math.round(r.x), y: Math.round(r.y),
                                            text: text,
                                            tag: el.tagName,
                                            classes: (el.className || '').toString().substring(0, 30),
                                        });
                                    }
                                }
                            }
                            result.canvasElements = canvasEls.sort(function(a,b){return a.y-b.y}).slice(0,15);

                            // Check all file inputs
                            result.fileInputs = [];
                            for (var inp of document.querySelectorAll('input[type="file"]')) {
                                result.fileInputs.push({accept: inp.accept || 'any'});
                            }

                            return result;
                        }""")

                        print(f"\n  === FINAL STATE ===", flush=True)
                        print(f"  Has dialog: {final_state.get('hasDialog')}", flush=True)
                        if final_state.get('dialogText'):
                            print(f"  Dialog text: {final_state['dialogText'][:100]}", flush=True)
                        if final_state.get('panelText'):
                            print(f"  Panel text: {final_state['panelText'][:200]}", flush=True)
                        if final_state.get('panelImgs'):
                            print(f"  Panel images: {final_state['panelImgs']}", flush=True)
                        print(f"  Audio elements: {final_state.get('audioElements', [])}", flush=True)
                        print(f"  Canvas elements:", flush=True)
                        for c in final_state.get('canvasElements', []):
                            print(f"    ({c['x']},{c['y']}) '{c['text']}' <{c['tag']}>", flush=True)
                        print(f"  File inputs: {final_state.get('fileInputs', [])}", flush=True)

    # ============================================================
    #  PART B: IMG2IMG — MODEL DROPDOWN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART B: IMG2IMG MODELS", flush=True)
    print("=" * 60, flush=True)

    # Close any panels/dialogs
    for _ in range(5):
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    page.wait_for_timeout(500)

    opened = open_tool_by_mouse(page, "Img2Img")
    if not opened:
        # Toggle approach
        print("  Retrying...", flush=True)
        open_tool_by_mouse(page, "Instant Storyboard")
        page.wait_for_timeout(1000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        open_tool_by_mouse(page, "Img2Img")

    ss(page, "P97_05_img2img")

    # Check for img2img panel
    i2i_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show.img2img-config-panel');
        return p ? 'open' : 'not open';
    }""")
    print(f"  Img2Img panel: {i2i_panel}", flush=True)

    if i2i_panel == 'open':
        # Click the model name area
        print("\n  Clicking model selector (mouse)...", flush=True)
        model_coords = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var style = panel.querySelector('.c-style');
            if (style) {
                var r = style.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
            return null;
        }""")
        if model_coords:
            page.mouse.click(model_coords['x'], model_coords['y'])
            print(f"  Clicked model at ({model_coords['x']},{model_coords['y']})", flush=True)
            page.wait_for_timeout(2000)
            ss(page, "P97_06_model_dropdown")

            # Check what opened
            style_panel = page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (slp) {
                    var r = slp.getBoundingClientRect();
                    return {
                        w: Math.round(r.width), h: Math.round(r.height),
                        x: Math.round(r.x), y: Math.round(r.y),
                        display: window.getComputedStyle(slp).display,
                        children: slp.children.length,
                    };
                }
                return null;
            }""")
            print(f"  Style panel: {style_panel}", flush=True)

            if style_panel and style_panel.get('w', 0) > 0:
                # Panel rendered! Read models
                models = page.evaluate("""() => {
                    var slp = document.querySelector('.style-list-panel');
                    if (!slp) return [];
                    var items = [];
                    for (var el of slp.querySelectorAll('.style-name, .style-item-name, [class*="name"]')) {
                        var text = (el.innerText || '').trim();
                        if (text.length > 2 && text.length < 50) items.push(text);
                    }
                    return [...new Set(items)];
                }""")
                print(f"\n  Models ({len(models)}):", flush=True)
                for m in models:
                    print(f"    {m}", flush=True)

            elif style_panel and style_panel.get('w', 0) == 0:
                # Width 0 — try force render
                print("  Width 0 — force rendering...", flush=True)
                models = page.evaluate("""() => {
                    var slp = document.querySelector('.style-list-panel');
                    if (!slp) return null;
                    slp.style.cssText = 'width:350px !important; display:flex !important; visibility:visible !important; overflow-y:auto !important; position:absolute !important; z-index:9999 !important; left:80px !important; top:50px !important; background:#1a1a1a !important; max-height:800px !important; flex-direction:column !important;';

                    // Wait for rendering
                    var items = [];
                    var seen = new Set();
                    for (var child of slp.querySelectorAll('*')) {
                        var text = (child.innerText || '').trim();
                        var cls = (child.className || '').toString();
                        var r = child.getBoundingClientRect();
                        if (text.length > 2 && text.length < 50
                            && !seen.has(text) && r.height < 50) {
                            seen.add(text);
                            items.push({
                                text: text,
                                tag: child.tagName,
                                y: Math.round(r.y),
                                classes: cls.substring(0, 30),
                            });
                        }
                    }
                    items.sort(function(a,b) { return a.y - b.y; });
                    return items;
                }""")
                ss(page, "P97_07_forced_panel")
                print(f"\n  Forced models ({len(models) if models else 0}):", flush=True)
                if models:
                    for m in models[:40]:
                        print(f"    y={m['y']} <{m['tag']}> c='{m['classes'][:20]}' '{m['text']}'", flush=True)

                # Reset
                page.evaluate("() => document.querySelector('.style-list-panel')?.removeAttribute('style')")
            else:
                print("  No style panel found at all", flush=True)

    ss(page, "P97_08_final")

    print(f"\n\n===== PHASE 97 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
