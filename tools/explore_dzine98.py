"""Phase 98: Fixed Lip Sync face flow + Img2Img model dropdown.
Fixes: case-insensitive check, close lip-sync-config-panel before switching.
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


def close_all_panels(page):
    """Reliably close all panels."""
    page.evaluate("""() => {
        // Close c-gen-config panel
        var c1 = document.querySelector('.c-gen-config.show .ico-close');
        if (c1) c1.click();
        // Close panels.show
        var c2 = document.querySelector('.panels.show .ico-close');
        if (c2) c2.click();
        // Close lip-sync-config-panel
        var lsp = document.querySelector('.lip-sync-config-panel.show .ico-close');
        if (lsp) lsp.click();
    }""")
    page.wait_for_timeout(500)
    # Escape for good measure
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)


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
    #  PART A: LIP SYNC — COMPLETE FACE → AUDIO FLOW
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART A: LIP SYNC — FACE SELECTION", flush=True)
    print("=" * 60, flush=True)

    # Open Lip Sync
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Verify panel
    ls_active = page.evaluate("""() => {
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        return lsp ? true : false;
    }""")
    print(f"  Lip Sync active: {ls_active}", flush=True)

    if ls_active:
        ss(page, "P98_01_lip_sync")

        # Find and click "Pick a Face Image" button
        pick_coords = page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button.pick-image')) {
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (text.includes('Face Image') && !text.includes('Video') && r.width > 100) {
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")
        print(f"  Pick face coords: {pick_coords}", flush=True)

        if pick_coords:
            page.mouse.click(pick_coords['x'], pick_coords['y'])
            page.wait_for_timeout(4000)
            close_dialogs(page)
            ss(page, "P98_02_pick_face_dialog")

            # Check for edit-image-dialog
            has_face_dialog = page.evaluate("""() => {
                var d = document.querySelector('.edit-image-dialog');
                if (d) {
                    // Wait for face detection text
                    for (var el of d.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (t.includes('face selected')) return t;
                    }
                    return 'dialog open but no face count';
                }
                return null;
            }""")
            print(f"  Face dialog: {has_face_dialog}", flush=True)

            if has_face_dialog:
                # STEP 1: Click Next (face detection → crop)
                print("\n  === STEP 1: Face → Crop ===", flush=True)
                n1 = page.evaluate("""() => {
                    var btns = document.querySelectorAll('button');
                    for (var btn of btns) {
                        var t = (btn.innerText || '').trim();
                        var r = btn.getBoundingClientRect();
                        if (t === 'Next' && r.width > 40 && r.y > 600 && r.height > 20) {
                            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                        }
                    }
                    return null;
                }""")
                if n1:
                    page.mouse.click(n1['x'], n1['y'])
                    page.wait_for_timeout(2000)
                    ss(page, "P98_03_crop_step")

                    # Verify crop step
                    crop_check = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var t = (el.innerText || '').trim();
                            if (t === 'How Cropping Works') return 'crop step confirmed';
                        }
                        return 'crop step not found';
                    }""")
                    print(f"  {crop_check}", flush=True)

                    # STEP 2: Click Next (crop → ?)
                    print("  === STEP 2: Crop → ? ===", flush=True)
                    n2 = page.evaluate("""() => {
                        var btns = document.querySelectorAll('button');
                        for (var btn of btns) {
                            var t = (btn.innerText || '').trim();
                            var r = btn.getBoundingClientRect();
                            if (t === 'Next' && r.width > 40 && r.y > 600 && r.height > 20) {
                                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                            }
                        }
                        return null;
                    }""")
                    if n2:
                        page.mouse.click(n2['x'], n2['y'])
                        page.wait_for_timeout(4000)
                        close_dialogs(page)
                        ss(page, "P98_04_after_crop_next")

                        # ===== CRITICAL: Map the new state =====
                        print("\n  === STATE AFTER SECOND NEXT ===", flush=True)

                        # 1. Check for another dialog
                        new_dialog = page.evaluate("""() => {
                            var d = document.querySelector('.edit-image-dialog');
                            if (d) {
                                var r = d.getBoundingClientRect();
                                if (r.width > 300) {
                                    var items = [];
                                    var seen = new Set();
                                    for (var child of d.querySelectorAll('*')) {
                                        var cr = child.getBoundingClientRect();
                                        var text = (child.innerText || '').trim();
                                        if (cr.width > 0 && cr.height > 0
                                            && text.length > 0 && text.length < 60
                                            && text.indexOf('\\n') === -1
                                            && cr.height < 60) {
                                            var key = text.substring(0,20) + '|' + Math.round(cr.y);
                                            if (!seen.has(key)) {
                                                seen.add(key);
                                                items.push({
                                                    tag: child.tagName,
                                                    x: Math.round(cr.x), y: Math.round(cr.y),
                                                    w: Math.round(cr.width), h: Math.round(cr.height),
                                                    text: text,
                                                    classes: (child.className || '').toString().substring(0, 30),
                                                });
                                            }
                                        }
                                    }
                                    items.sort(function(a,b){return a.y - b.y});
                                    return items.slice(0, 25);
                                }
                            }
                            return null;
                        }""")
                        if new_dialog:
                            print(f"  Dialog still open ({len(new_dialog)} elements):", flush=True)
                            for e in new_dialog:
                                print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text']}' c='{e['classes'][:20]}'", flush=True)
                        else:
                            print(f"  Dialog closed!", flush=True)

                        # 2. Check panel
                        panel_text = page.evaluate("""() => {
                            var p = document.querySelector('.c-gen-config.show');
                            return p ? (p.innerText || '').trim().substring(0, 400) : null;
                        }""")
                        print(f"\n  Panel text: {panel_text[:200] if panel_text else 'None'}", flush=True)

                        # 3. Check if face is now set (warning removed)
                        has_warning = panel_text and 'Please pick' in panel_text if panel_text else True
                        print(f"  Still has 'Please pick' warning: {has_warning}", flush=True)

                        # 4. Check for face preview and audio upload
                        face_and_audio = page.evaluate("""() => {
                            var result = {facePreview: null, audioUpload: null, canvasElements: []};

                            var p = document.querySelector('.c-gen-config.show');
                            if (p) {
                                // Face preview image
                                for (var img of p.querySelectorAll('img')) {
                                    var r = img.getBoundingClientRect();
                                    var src = img.src || '';
                                    if (r.width > 40 && r.height > 40 && src.includes('stylar_product')) {
                                        result.facePreview = {
                                            src: src.substring(0, 100),
                                            w: Math.round(r.width), h: Math.round(r.height),
                                        };
                                    }
                                }

                                // Audio elements
                                for (var el of p.querySelectorAll('*')) {
                                    var cls = (el.className || '').toString();
                                    var text = (el.innerText || '').trim();
                                    if (cls.includes('audio') || cls.includes('voice')
                                        || text.includes('Audio') || text.includes('audio')) {
                                        var r = el.getBoundingClientRect();
                                        if (r.width > 0) {
                                            result.audioUpload = {
                                                classes: cls.substring(0, 40),
                                                text: text.substring(0, 60),
                                            };
                                        }
                                    }
                                }
                            }

                            // Canvas center
                            var seen = new Set();
                            for (var el of document.querySelectorAll('*')) {
                                var r = el.getBoundingClientRect();
                                var text = (el.innerText || '').trim();
                                if (r.x > 350 && r.x < 1050 && r.y > 100 && r.y < 800
                                    && r.width > 50 && r.height > 15
                                    && text.length > 0 && text.length < 60
                                    && text.indexOf('\\n') === -1
                                    && r.height < 80) {
                                    var key = text.substring(0,20) + '|' + Math.round(r.y/10);
                                    if (!seen.has(key)) {
                                        seen.add(key);
                                        result.canvasElements.push({
                                            x: Math.round(r.x), y: Math.round(r.y),
                                            text: text, tag: el.tagName,
                                            classes: (el.className || '').toString().substring(0, 30),
                                        });
                                    }
                                }
                            }
                            result.canvasElements.sort(function(a,b){return a.y-b.y});
                            result.canvasElements = result.canvasElements.slice(0, 15);
                            return result;
                        }""")
                        print(f"\n  Face preview: {face_and_audio.get('facePreview')}", flush=True)
                        print(f"  Audio upload: {face_and_audio.get('audioUpload')}", flush=True)
                        print(f"  Canvas:", flush=True)
                        for c in face_and_audio.get('canvasElements', []):
                            print(f"    ({c['x']},{c['y']}) '{c['text']}' <{c['tag']}> c='{c['classes'][:20]}'", flush=True)

    # ============================================================
    #  PART B: IMG2IMG — CLOSE LIP SYNC FIRST, THEN OPEN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART B: IMG2IMG", flush=True)
    print("=" * 60, flush=True)

    # Close the Lip Sync panel properly
    close_all_panels(page)
    page.wait_for_timeout(1000)

    # Verify closed
    any_panel = page.evaluate("""() => {
        return !!(document.querySelector('.c-gen-config.show') ||
                  document.querySelector('.lip-sync-config-panel.show') ||
                  document.querySelector('.panels.show'));
    }""")
    print(f"  Any panel open: {any_panel}", flush=True)

    if any_panel:
        # Force close
        page.evaluate("""() => {
            var panels = document.querySelectorAll('.c-gen-config.show, .lip-sync-config-panel.show, .panels.show');
            for (var p of panels) {
                p.classList.remove('show');
            }
        }""")
        page.wait_for_timeout(500)

    # Now click Img2Img
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P98_05_img2img")

    # Check panel
    i2i_open = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return 'no panel';
        var cls = (p.className || '').toString();
        if (cls.includes('img2img')) return 'img2img open';
        var h = p.querySelector('.gen-config-header');
        return h ? 'panel: ' + (h.innerText || '').trim() : 'unknown panel';
    }""")
    print(f"  Panel: {i2i_open}", flush=True)

    if 'img2img' in i2i_open:
        # Click model selector
        model_coords = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var style = panel?.querySelector('.c-style');
            if (!style) return null;
            var r = style.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        if model_coords:
            page.mouse.click(model_coords['x'], model_coords['y'])
            print(f"  Clicked model at ({model_coords['x']},{model_coords['y']})", flush=True)
            page.wait_for_timeout(2000)
            ss(page, "P98_06_model_click")

            # Read style-list-panel
            slp_info = page.evaluate("""() => {
                var slp = document.querySelector('.style-list-panel');
                if (!slp) return {exists: false};
                var r = slp.getBoundingClientRect();
                var cs = window.getComputedStyle(slp);
                return {
                    exists: true,
                    w: Math.round(r.width), h: Math.round(r.height),
                    display: cs.display, visibility: cs.visibility,
                    overflow: cs.overflow, position: cs.position,
                    childCount: slp.children.length,
                    innerHTML_length: slp.innerHTML.length,
                };
            }""")
            print(f"\n  style-list-panel: {slp_info}", flush=True)

            if slp_info.get('exists') and slp_info.get('innerHTML_length', 0) > 100:
                # Has content but width=0 — force visible and read models
                print("  Forcing panel visible...", flush=True)
                models_data = page.evaluate("""() => {
                    var slp = document.querySelector('.style-list-panel');
                    if (!slp) return null;
                    slp.style.cssText = 'width:350px !important; height:800px !important; display:block !important; visibility:visible !important; overflow-y:auto !important; position:absolute !important; z-index:9999 !important; left:80px !important; top:50px !important; background:#1a1a1a !important;';

                    // Read all model/style names
                    var items = [];
                    var seen = new Set();
                    for (var el of slp.querySelectorAll('.style-item, [class*="item"]')) {
                        var name = '';
                        var nameEl = el.querySelector('.style-name, [class*="name"]');
                        if (nameEl) name = (nameEl.innerText || '').trim();
                        if (!name) name = (el.innerText || '').trim();
                        if (name.length > 2 && name.length < 50 && !seen.has(name)) {
                            seen.add(name);
                            items.push(name);
                        }
                    }
                    // Also try direct text nodes
                    if (items.length < 5) {
                        for (var el of slp.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            if (text.length > 3 && text.length < 40
                                && !text.includes('\\n') && !seen.has(text)) {
                                seen.add(text);
                                items.push(text);
                            }
                        }
                    }
                    return items.slice(0, 50);
                }""")
                page.wait_for_timeout(500)
                ss(page, "P98_07_models_forced")
                print(f"\n  Models ({len(models_data) if models_data else 0}):", flush=True)
                if models_data:
                    for m in models_data:
                        print(f"    {m}", flush=True)

                # Reset
                page.evaluate("() => document.querySelector('.style-list-panel')?.removeAttribute('style')")

    ss(page, "P98_08_final")
    print(f"\n\n===== PHASE 98 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
