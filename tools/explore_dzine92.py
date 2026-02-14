"""Phase 92: Lip Sync FULL WORKFLOW — face pick → audio → generate.
Goal: Complete end-to-end Lip Sync automation test.
1. Open Lip Sync, click result to get "Pick a Face" dialog
2. Click "Next" to proceed past face selection
3. Map the audio upload step
4. Try uploading a test audio file
5. Understand the complete Lip Sync pipeline
Also: Img2Img panel deep dive (style selector workaround)
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


def close_all_overlays(page):
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.evaluate("""() => {
        var c1 = document.querySelector('.c-gen-config.show .ico-close');
        if (c1) c1.click();
        var c2 = document.querySelector('.panels.show .ico-close');
        if (c2) c2.click();
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)
    page.mouse.click(700, 450)
    page.wait_for_timeout(500)


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
    #  STEP 1: Open Lip Sync panel
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: OPEN LIP SYNC", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Toggle via distant tool, then click Lip Sync
    page.mouse.click(40, 766)  # Storyboard
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)

    page.mouse.click(40, 400)  # Lip Sync
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P92_01_lip_sync_panel")

    # Check if panel opened
    panel_check = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return 'no panel';
        return (p.innerText || '').trim().substring(0, 100);
    }""")
    print(f"  Panel: {panel_check}", flush=True)

    # ============================================================
    #  STEP 2: Click "Pick a Face Image" on canvas
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: PICK A FACE IMAGE (from canvas)", flush=True)
    print("=" * 60, flush=True)

    # The canvas shows "Pick a Face Image" and "Upload a Face Video"
    # Try clicking "Pick a Face Image" button
    pick_face = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Pick a Face Image' && r.width > 100 && r.x > 400) {
                el.click();
                return 'clicked Pick a Face Image at (' + Math.round(r.x) + ',' + Math.round(r.y) + ')';
            }
        }
        return 'not found';
    }""")
    print(f"  Pick face: {pick_face}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    ss(page, "P92_02_pick_face_dialog")

    # Map the dialog that appeared
    dialog_items = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 200 && r.height > 100) {
                // Found the overlay container
                var cls = (el.className || '').toString();
                items.push({
                    type: 'container', z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: cls.substring(0, 60),
                });

                // Map children
                for (var child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    var ctag = child.tagName;
                    // Only meaningful elements
                    if ((ctag === 'BUTTON' || ctag === 'INPUT' || ctag === 'IMG'
                        || (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1
                            && cr.width > 10 && cr.height > 8 && cr.height < 60))
                        && cr.width > 0) {
                        var key = text + '|' + Math.round(cr.y) + '|' + ctag;
                        if (!seen.has(key)) {
                            seen.add(key);
                            items.push({
                                type: 'child', tag: ctag,
                                x: Math.round(cr.x), y: Math.round(cr.y),
                                w: Math.round(cr.width), h: Math.round(cr.height),
                                text: text.substring(0, 50),
                                classes: (child.className || '').toString().substring(0, 40),
                            });
                        }
                    }
                }
                break;
            }
        }
        return items;
    }""")
    print(f"\n  Dialog elements ({len(dialog_items)}):", flush=True)
    for d in dialog_items[:30]:
        if d.get('type') == 'container':
            print(f"  [CONTAINER] z={d['z']} ({d['x']},{d['y']}) {d['w']}x{d['h']} c='{d['classes'][:50]}'", flush=True)
        else:
            print(f"    ({d['x']},{d['y']}) {d['w']}x{d['h']} <{d['tag']}> c='{d.get('classes','')[:25]}' '{d.get('text','')}'", flush=True)

    # ============================================================
    #  STEP 3: Select face from results (if dialog shows results)
    #  OR: Upload a face from local file
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: FACE SELECTION OPTIONS", flush=True)
    print("=" * 60, flush=True)

    # Check if there are tabs in the dialog (like "Results", "Uploads")
    dialog_tabs = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            if (z > 500) {
                var r = el.getBoundingClientRect();
                if (r.width > 200) {
                    for (var tab of el.querySelectorAll('[class*="tab"], [class*="header-item"], [role="tab"]')) {
                        var tr = tab.getBoundingClientRect();
                        items.push({
                            x: Math.round(tr.x), y: Math.round(tr.y),
                            w: Math.round(tr.width), h: Math.round(tr.height),
                            text: (tab.innerText || '').trim().substring(0, 30),
                            classes: (tab.className || '').toString().substring(0, 40),
                        });
                    }
                    break;
                }
            }
        }
        return items;
    }""")
    print(f"  Dialog tabs: {dialog_tabs}", flush=True)

    # Look for image thumbnails in the dialog (generated results we can pick from)
    dialog_images = page.evaluate("""() => {
        var imgs = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            if (z > 500) {
                var r = el.getBoundingClientRect();
                if (r.width > 200) {
                    for (var img of el.querySelectorAll('img')) {
                        var ir = img.getBoundingClientRect();
                        if (ir.width > 30 && ir.height > 30) {
                            imgs.push({
                                src: (img.src || '').substring(0, 120),
                                x: Math.round(ir.x), y: Math.round(ir.y),
                                w: Math.round(ir.width), h: Math.round(ir.height),
                            });
                        }
                    }
                    break;
                }
            }
        }
        return imgs;
    }""")
    print(f"\n  Dialog images ({len(dialog_images)}):", flush=True)
    for img in dialog_images[:10]:
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src']}", flush=True)

    # Click the first result image to select it as face
    if dialog_images:
        first_img = dialog_images[0]
        cx = first_img['x'] + first_img['w'] // 2
        cy = first_img['y'] + first_img['h'] // 2
        page.mouse.click(cx, cy)
        print(f"\n  Clicked image at ({cx},{cy})", flush=True)
        page.wait_for_timeout(2000)
        ss(page, "P92_03_face_selected")

        # Check for face detection overlay (yellow rectangle)
        face_detected = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                if (z > 500) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 200 && r.height > 200) {
                        // Look for face selection indicators
                        for (var child of el.querySelectorAll('[class*="face"], [class*="mark"], [class*="selected"]')) {
                            var cr = child.getBoundingClientRect();
                            items.push({
                                x: Math.round(cr.x), y: Math.round(cr.y),
                                w: Math.round(cr.width), h: Math.round(cr.height),
                                classes: (child.className || '').toString().substring(0, 40),
                                text: (child.innerText || '').trim().substring(0, 30),
                            });
                        }
                        // Also check for "Next" button
                        for (var btn of el.querySelectorAll('button')) {
                            var bt = (btn.innerText || '').trim();
                            if (bt === 'Next' || bt === 'Confirm' || bt === 'Cancel') {
                                var br = btn.getBoundingClientRect();
                                items.push({
                                    x: Math.round(br.x), y: Math.round(br.y),
                                    w: Math.round(br.width), h: Math.round(br.height),
                                    classes: 'BUTTON',
                                    text: bt,
                                });
                            }
                        }
                        // Check status text
                        for (var txt of el.querySelectorAll('*')) {
                            var t = (txt.innerText || '').trim();
                            if (t.includes('face selected') || t.includes('Up to')) {
                                items.push({
                                    x: 0, y: 0, w: 0, h: 0,
                                    classes: 'STATUS',
                                    text: t.substring(0, 50),
                                });
                            }
                        }
                        break;
                    }
                }
            }
            return items;
        }""")
        print(f"\n  Face detection:", flush=True)
        for f in face_detected:
            print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']} '{f['classes']}' '{f['text']}'", flush=True)

        # ============================================================
        #  STEP 4: Click "Next" to proceed to audio step
        # ============================================================
        print("\n" + "=" * 60, flush=True)
        print("  STEP 4: CLICK NEXT → AUDIO UPLOAD", flush=True)
        print("=" * 60, flush=True)

        next_clicked = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                if (z > 500) {
                    for (var btn of el.querySelectorAll('button')) {
                        var text = (btn.innerText || '').trim();
                        if (text === 'Next') {
                            btn.click();
                            return 'clicked Next';
                        }
                    }
                }
            }
            return 'Next not found';
        }""")
        print(f"  Next: {next_clicked}", flush=True)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        ss(page, "P92_04_audio_step")

        # Map the audio upload step
        audio_step = page.evaluate("""() => {
            var items = [];
            var seen = new Set();

            // Check for high-z overlay (dialog)
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 500 && r.width > 200 && r.height > 100) {
                    items.push({
                        type: 'container', z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 60),
                    });

                    for (var child of el.querySelectorAll('*')) {
                        var cr = child.getBoundingClientRect();
                        var text = (child.innerText || '').trim();
                        var ctag = child.tagName;
                        if ((ctag === 'BUTTON' || ctag === 'INPUT' || ctag === 'TEXTAREA'
                            || ctag === 'SELECT' || ctag === 'LABEL'
                            || (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1
                                && cr.width > 10 && cr.height > 8 && cr.height < 80))
                            && cr.width > 0) {
                            var key = text + '|' + Math.round(cr.y) + '|' + ctag;
                            if (!seen.has(key)) {
                                seen.add(key);
                                items.push({
                                    type: 'child', tag: ctag,
                                    x: Math.round(cr.x), y: Math.round(cr.y),
                                    w: Math.round(cr.width), h: Math.round(cr.height),
                                    text: text.substring(0, 60),
                                    classes: (child.className || '').toString().substring(0, 40),
                                    inputType: child.type || '',
                                    accept: child.accept || '',
                                });
                            }
                        }
                    }
                    break;
                }
            }

            // Also check Lip Sync panel state
            var lsp = document.querySelector('.lip-sync-operation-panel') ||
                      document.querySelector('.c-gen-config.show');
            if (lsp) {
                var lr = lsp.getBoundingClientRect();
                items.push({
                    type: 'panel',
                    x: Math.round(lr.x), y: Math.round(lr.y),
                    w: Math.round(lr.width), h: Math.round(lr.height),
                    text: (lsp.innerText || '').trim().substring(0, 200),
                    classes: (lsp.className || '').toString().substring(0, 60),
                });
            }
            return items;
        }""")
        print(f"\n  Audio step elements ({len(audio_step)}):", flush=True)
        for a in audio_step:
            if a.get('type') == 'container':
                print(f"  [CONTAINER] z={a['z']} ({a['x']},{a['y']}) {a['w']}x{a['h']} c='{a['classes'][:50]}'", flush=True)
            elif a.get('type') == 'panel':
                print(f"  [PANEL] ({a['x']},{a['y']}) {a['w']}x{a['h']} c='{a['classes'][:50]}'", flush=True)
                print(f"    text: {a['text'][:150]}", flush=True)
            else:
                extra = ""
                if a.get('inputType'):
                    extra += f" type={a['inputType']}"
                if a.get('accept'):
                    extra += f" accept={a['accept']}"
                print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> c='{a.get('classes','')[:25]}' '{a.get('text','')[:40]}'{extra}", flush=True)

    else:
        print("  No dialog images found, trying alternative approach...", flush=True)
        # Try clicking on the Lip Sync action from Results panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  STEP 5: Check for audio upload area in the dialog/panel
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 5: AUDIO UPLOAD AREA", flush=True)
    print("=" * 60, flush=True)

    # After clicking Next, there should be an audio upload section
    # Look for file inputs, upload buttons, or drag zones
    audio_area = page.evaluate("""() => {
        var items = [];
        // Check everywhere for audio-related elements
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var cls = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.x > 0) {
                if (cls.includes('audio') || cls.includes('upload-audio')
                    || cls.includes('lip-sync-audio') || cls.includes('voice-upload')
                    || text.includes('Upload Audio') || text.includes('Upload Voice')
                    || text.includes('Record') || text.includes('.mp3')
                    || text.includes('.wav') || text.includes('audio')) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: cls.substring(0, 50),
                        text: text.substring(0, 60),
                    });
                }
            }
        }
        // Also check all visible file inputs
        for (var inp of document.querySelectorAll('input')) {
            var r = inp.getBoundingClientRect();
            if (r.width > 0 || inp.type === 'file') {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: 'INPUT',
                    classes: (inp.className || '').toString().substring(0, 50),
                    text: 'type=' + (inp.type || '') + ' accept=' + (inp.accept || ''),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Audio upload elements ({len(audio_area)}):", flush=True)
    for a in audio_area[:20]:
        print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> c='{a['classes'][:35]}' '{a['text'][:45]}'", flush=True)

    # ============================================================
    #  STEP 6: Img2Img Panel — Model Selector + Style Workaround
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 6: IMG2IMG DEEP DIVE", flush=True)
    print("=" * 60, flush=True)

    # Close any overlays
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    close_all_overlays(page)
    page.wait_for_timeout(1000)

    # Open Img2Img
    page.mouse.click(40, 766)  # Storyboard first
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(500)

    page.mouse.click(40, 240)  # Img2Img
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Verify we have img2img panel
    i2i_check = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show.img2img-config-panel');
        if (p) return 'img2img panel open';
        var p2 = document.querySelector('.c-gen-config.show');
        if (p2) return 'panel: ' + (p2.className || '').toString().substring(0, 60);
        return 'no panel';
    }""")
    print(f"  Panel: {i2i_check}", flush=True)

    # Deep dive into Img2Img panel structure
    i2i_detail = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;

        var items = [];
        var seen = new Set();

        // Get all interactive elements and labels
        for (var child of panel.querySelectorAll('*')) {
            var r = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            var cls = (child.className || '').toString();
            var tag = child.tagName;

            // Labels, buttons, selectors, options
            if (r.width > 0 && r.height > 0 && r.height < 80
                && (tag === 'BUTTON' || tag === 'INPUT' || tag === 'SELECT'
                    || cls.includes('option') || cls.includes('label')
                    || cls.includes('model') || cls.includes('style')
                    || cls.includes('ratio') || cls.includes('slider')
                    || cls.includes('strength') || cls.includes('prompt')
                    || cls.includes('textarea') || cls.includes('select')
                    || (text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1))) {
                var key = text + '|' + Math.round(r.y) + '|' + tag;
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: tag, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 50),
                        classes: cls.substring(0, 50),
                    });
                }
            }
        }
        // Sort by y position
        items.sort(function(a,b) { return a.y - b.y; });
        return items;
    }""")
    print(f"\n  Img2Img elements ({len(i2i_detail) if i2i_detail else 0}):", flush=True)
    if i2i_detail:
        for item in i2i_detail[:40]:
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> "
                  f"c='{item['classes'][:30]}' '{item['text']}'", flush=True)

    ss(page, "P92_05_img2img")

    # Try clicking the model selector (like in Chat Editor — .option-label approach)
    model_click = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'no panel';
        // Look for model-related elements
        for (var el of panel.querySelectorAll('.option-label, [class*="model"], [class*="select"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.width > 50 && r.height > 10 && r.height < 40 && text.length > 2 && text.length < 40) {
                return {
                    text: text, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return 'not found';
    }""")
    print(f"\n  Model selector: {model_click}", flush=True)

    # Try the "Style" button click — the persistent width=0 issue
    # This time, try scrolling the panel first and clicking directly
    style_info = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'no panel';
        var results = [];
        for (var el of panel.querySelectorAll('*')) {
            var cls = (el.className || '').toString();
            var text = (el.innerText || '').trim();
            if (cls.includes('style') || text === 'Style' || text === 'No Style'
                || text === 'No Style v2') {
                var r = el.getBoundingClientRect();
                results.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 30),
                    classes: cls.substring(0, 50),
                });
            }
        }
        return results;
    }""")
    print(f"\n  Style elements ({len(style_info) if isinstance(style_info, list) else 0}):", flush=True)
    if isinstance(style_info, list):
        for s in style_info:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> c='{s['classes'][:35]}' '{s['text']}'", flush=True)

    # ============================================================
    #  STEP 7: Img2Img — Upload image area
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 7: IMG2IMG UPLOAD AREA", flush=True)
    print("=" * 60, flush=True)

    # The Img2Img needs a source image. Check how to upload/select
    upload_area = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var items = [];
        for (var el of panel.querySelectorAll('[class*="upload"], [class*="pick"], [class*="drop"], [class*="source"], [class*="input-image"], button')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.width > 0 && r.height > 0) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 50),
                    text: text.substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Upload area elements ({len(upload_area) if upload_area else 0}):", flush=True)
    if upload_area:
        for u in upload_area[:20]:
            print(f"    ({u['x']},{u['y']}) {u['w']}x{u['h']} <{u['tag']}> c='{u['classes'][:35]}' '{u['text'][:30]}'", flush=True)

    ss(page, "P92_06_img2img_detail")

    print(f"\n\n===== PHASE 92 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
