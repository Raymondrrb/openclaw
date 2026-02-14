"""Phase 101: Complete Lip Sync face selection — fix Pick Image dialog detection.
A) Open Lip Sync → click Pick Face → dump FULL dialog DOM structure
B) Find & click canvas thumbnail → face detect → crop → face set in panel
C) Once face is set, map what audio upload UI appears
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
    print("\n=== STEP 1: Open Lip Sync ===", flush=True)
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Confirm it opened
    is_open = page.evaluate("""() => {
        var p = document.querySelector('.lip-sync-config-panel.show');
        return p ? true : false;
    }""")
    print(f"  Lip Sync panel open: {is_open}", flush=True)
    if not is_open:
        print("  ABORT: Lip Sync panel did not open", flush=True)
        sys.stdout.flush()
        os._exit(1)

    # ============================================================
    #  STEP 2: Click "Pick a Face Image" button
    # ============================================================
    print("\n=== STEP 2: Click Pick a Face Image ===", flush=True)

    # First map ALL pick buttons
    pick_btns = page.evaluate("""() => {
        var btns = [];
        for (var b of document.querySelectorAll('button.pick-image')) {
            var r = b.getBoundingClientRect();
            var text = (b.innerText || '').trim();
            btns.push({
                text: text, x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
                isVideo: b.classList.contains('pick-video'),
            });
        }
        return btns;
    }""")
    print(f"  Pick buttons: {json.dumps(pick_btns, indent=2)}", flush=True)

    # Click the face image button (not video)
    face_btn = None
    for b in pick_btns:
        if not b['isVideo'] and b['w'] > 50:
            face_btn = b
            break

    if not face_btn:
        print("  ABORT: No face image button found", flush=True)
        sys.stdout.flush()
        os._exit(1)

    page.mouse.click(face_btn['x'], face_btn['y'])
    print(f"  Clicked at ({face_btn['x']},{face_btn['y']})", flush=True)
    page.wait_for_timeout(3000)
    ss(page, "P101_01_after_pick_click")

    # ============================================================
    #  STEP 3: FULLY map the Pick Image dialog
    # ============================================================
    print("\n=== STEP 3: Map Pick Image dialog DOM ===", flush=True)

    # Find ALL high-z overlays/dialogs
    dialog_info = page.evaluate("""() => {
        var dialogs = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 100 && r.width > 200 && r.height > 200 && r.x > 50) {
                var text = (el.innerText || '').substring(0, 300);
                dialogs.push({
                    tag: el.tagName, class: (el.className||'').toString().substring(0,100),
                    z: z, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 150),
                    hasImgs: el.querySelectorAll('img').length,
                    hasBtns: el.querySelectorAll('button').length,
                    hasInputs: el.querySelectorAll('input[type="file"]').length,
                });
            }
        }
        dialogs.sort(function(a,b){return b.z - a.z});
        return dialogs.slice(0, 10);
    }""")
    print(f"  High-z overlays ({len(dialog_info)}):", flush=True)
    for d in dialog_info:
        print(f"    z={d['z']} <{d['tag']}> .{d['class'][:60]}", flush=True)
        print(f"      ({d['x']},{d['y']}) {d['w']}x{d['h']}  imgs={d['hasImgs']} btns={d['hasBtns']} inputs={d['hasInputs']}", flush=True)
        print(f"      text: {d['text'][:80]}", flush=True)

    # Now find ANY dialog with "choose an image" or "canvas" or "Pick Image" text
    pick_dialog = page.evaluate("""() => {
        // Search by text content
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.width > 300 && r.height > 200
                && (text.includes('choose an image on the canvas')
                    || text.includes('Drop or select')
                    || text.includes('Pick Image'))) {
                // Found the dialog! Now map its children.
                var children = [];
                for (var child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    if (cr.width < 5 || cr.height < 5) continue;
                    var ct = (child.innerText || '').trim();
                    var cls = (child.className || '').toString();
                    var tag = child.tagName;

                    // Only log interesting elements
                    if (tag === 'IMG' || tag === 'BUTTON' || tag === 'INPUT'
                        || tag === 'DIV' && (cr.width > 50 && cr.height > 50 && cr.y > 300)
                        || cls.includes('thumb') || cls.includes('canvas')
                        || cls.includes('image') || cls.includes('pick')
                        || cls.includes('layer')) {
                        children.push({
                            tag: tag,
                            class: cls.substring(0, 60),
                            src: tag === 'IMG' ? (child.src || '').substring(0, 100) : undefined,
                            x: Math.round(cr.x), y: Math.round(cr.y),
                            w: Math.round(cr.width), h: Math.round(cr.height),
                            text: ct.substring(0, 50),
                            clickable: tag === 'BUTTON' || tag === 'A'
                                || child.onclick !== null
                                || window.getComputedStyle(child).cursor === 'pointer',
                        });
                    }
                }
                // Sort by y position
                children.sort(function(a,b){return a.y - b.y});

                return {
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 100),
                    rect: {x: Math.round(r.x), y: Math.round(r.y),
                           w: Math.round(r.width), h: Math.round(r.height)},
                    z: parseInt(window.getComputedStyle(el).zIndex) || 0,
                    children: children.slice(0, 40),
                };
            }
        }
        return null;
    }""")

    if pick_dialog:
        print(f"\n  PICK DIALOG FOUND:", flush=True)
        print(f"    <{pick_dialog['tag']}> .{pick_dialog['class'][:60]}", flush=True)
        print(f"    rect: ({pick_dialog['rect']['x']},{pick_dialog['rect']['y']}) {pick_dialog['rect']['w']}x{pick_dialog['rect']['h']}", flush=True)
        print(f"    z: {pick_dialog['z']}", flush=True)
        print(f"\n    Children ({len(pick_dialog['children'])}):", flush=True)
        for c in pick_dialog['children']:
            extra = f" src={c.get('src','')}" if c.get('src') else ""
            click = " [CLICKABLE]" if c.get('clickable') else ""
            print(f"      ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> .{c['class'][:40]} '{c['text'][:30]}'{extra}{click}", flush=True)
    else:
        print("  Pick dialog NOT found by text search!", flush=True)

        # Fallback: just dump ALL visible imgs on page
        print("\n  Fallback: All visible images on page:", flush=True)
        all_imgs = page.evaluate("""() => {
            var imgs = [];
            for (var img of document.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.width > 30 && r.height > 30) {
                    imgs.push({
                        src: (img.src || '').substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cursor: window.getComputedStyle(img).cursor,
                        parentClass: (img.parentElement?.className || '').toString().substring(0, 40),
                    });
                }
            }
            return imgs;
        }""")
        for img in all_imgs:
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} cursor={img['cursor']} p=.{img['parentClass']} src={img['src'][:60]}", flush=True)

    # ============================================================
    #  STEP 4: Click the first canvas thumbnail
    # ============================================================
    print("\n=== STEP 4: Click canvas thumbnail ===", flush=True)

    # Try to find and click a thumbnail in the pick dialog
    # Use multiple strategies:
    thumb_coords = page.evaluate("""() => {
        // Strategy 1: Find images inside a dialog-like container
        // that are below the "choose an image on the canvas" text
        var canvasText = null;
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t === 'Or choose an image on the canvas' || t.includes('choose an image on the canvas')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100) canvasText = r;
            }
        }

        if (canvasText) {
            // Find images BELOW this text
            var imgs = [];
            for (var img of document.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.y > canvasText.y && r.width > 30 && r.height > 30 && r.width < 300) {
                    imgs.push({
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        src: (img.src || '').substring(0, 100),
                    });
                }
            }
            if (imgs.length > 0) return {strategy: 'below-canvas-text', thumb: imgs[0], total: imgs.length};
        }

        // Strategy 2: Find clickable divs/elements with background-image in the dialog area
        var clickables = [];
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            var bg = cs.backgroundImage || '';
            if (r.width > 50 && r.height > 50 && r.width < 300 && r.y > 300 && r.y < 700
                && bg !== 'none' && bg !== '' && cs.cursor === 'pointer') {
                clickables.push({
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    bg: bg.substring(0, 100),
                    class: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        if (clickables.length > 0) return {strategy: 'bg-image-clickable', thumb: clickables[0], total: clickables.length};

        // Strategy 3: Find any container with "layer" or "thumb" class near the dialog
        var layerEls = [];
        for (var el of document.querySelectorAll('[class*="layer"], [class*="thumb"], [class*="canvas-item"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 30 && r.height > 30 && r.y > 200 && r.y < 700) {
                layerEls.push({
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    class: (el.className || '').toString().substring(0, 60),
                });
            }
        }
        if (layerEls.length > 0) return {strategy: 'layer-class', thumb: layerEls[0], total: layerEls.length};

        return null;
    }""")

    if thumb_coords:
        t = thumb_coords['thumb']
        print(f"  Strategy: {thumb_coords['strategy']} ({thumb_coords['total']} found)", flush=True)
        print(f"  Clicking at ({t['x']},{t['y']}) {t['w']}x{t['h']}", flush=True)
        if t.get('src'):
            print(f"    src: {t['src'][:80]}", flush=True)
        if t.get('bg'):
            print(f"    bg: {t['bg'][:80]}", flush=True)
        if t.get('class'):
            print(f"    class: {t['class']}", flush=True)

        page.mouse.click(t['x'], t['y'])
        page.wait_for_timeout(4000)
        ss(page, "P101_02_after_thumb_click")
    else:
        print("  No thumbnail found! Trying raw coordinate click on screenshot...", flush=True)
        # Look at the screenshot to see where thumbnails are
        # From P98_02 and P100_02, the dialog center is roughly at page center
        # Canvas thumbnails appear roughly at y=500-600, x=500-700
        # Let's dump the exact center area
        center_elements = page.evaluate("""() => {
            var els = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                // Dialog center area
                if (r.x > 400 && r.x < 1000 && r.y > 350 && r.y < 700
                    && r.width > 20 && r.height > 20 && r.width < 400 && r.height < 400) {
                    var cs = window.getComputedStyle(el);
                    var bg = cs.backgroundImage || '';
                    var tag = el.tagName;
                    var cls = (el.className || '').toString();
                    var text = (el.innerText || '').trim();
                    if (tag === 'IMG' || bg !== 'none' || cls.includes('image')
                        || cls.includes('pick') || cls.includes('layer')
                        || cls.includes('thumb') || tag === 'CANVAS'
                        || (text.length > 0 && text.length < 50)) {
                        els.push({
                            tag: tag, class: cls.substring(0, 50),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            bg: bg.substring(0, 80),
                            cursor: cs.cursor,
                        });
                    }
                }
            }
            els.sort(function(a,b){return a.y - b.y});
            return els.slice(0, 30);
        }""")
        print(f"\n  Center area elements ({len(center_elements)}):", flush=True)
        for e in center_elements:
            bg = f" bg={e['bg']}" if e['bg'] != 'none' and e['bg'] else ""
            print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> .{e['class'][:35]} '{e['text'][:25]}' cur={e['cursor']}{bg}", flush=True)
        ss(page, "P101_02_no_thumb_debug")

    # ============================================================
    #  STEP 5: Handle face detection dialog (if we got here)
    # ============================================================
    print("\n=== STEP 5: Face detection dialog ===", flush=True)

    face_dialog = page.evaluate("""() => {
        // Check for edit-image-dialog
        var eid = document.querySelector('.edit-image-dialog');
        if (eid) {
            var r = eid.getBoundingClientRect();
            return {found: 'edit-image-dialog', x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (eid.innerText || '').substring(0, 200)};
        }
        // Check for "face selected" text
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.includes('face selected') || t === 'Mark Face Manually') {
                var r = el.getBoundingClientRect();
                return {found: 'face-text', text: t.substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return {found: false};
    }""")
    print(f"  Face dialog: {json.dumps(face_dialog)}", flush=True)

    if face_dialog.get('found') and face_dialog['found'] != False:
        # Click Next (face → crop)
        print("  Clicking Next (face → crop)...", flush=True)
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Next') {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        ss(page, "P101_03_crop_step")

        # Click Next (crop → done)
        print("  Clicking Next (crop → done)...", flush=True)
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Next') {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(5000)
        close_dialogs(page)
        ss(page, "P101_04_face_set")

        # ============================================================
        #  STEP 6: Check panel state after face is set
        # ============================================================
        print("\n=== STEP 6: Panel state after face set ===", flush=True)

        panel_full = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return null;
            var items = [];
            for (var child of p.querySelectorAll('*')) {
                var r = child.getBoundingClientRect();
                if (r.width < 5 || r.height < 5) continue;
                var text = (child.innerText || '').trim();
                var cls = (child.className || '').toString();
                var tag = child.tagName;
                var cs = window.getComputedStyle(child);
                if (text.length > 0 || tag === 'IMG' || tag === 'BUTTON'
                    || tag === 'INPUT' || cls.includes('audio') || cls.includes('voice')
                    || cls.includes('upload') || cls.includes('timeline')) {
                    items.push({
                        tag: tag, class: cls.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 50),
                        vis: cs.display !== 'none' && cs.visibility !== 'hidden',
                    });
                }
            }
            items.sort(function(a,b){return a.y - b.y});
            return {
                warning: (p.innerText || '').includes('Please pick'),
                items: items.slice(0, 40),
            };
        }""")

        if panel_full:
            print(f"  Warning still showing: {panel_full['warning']}", flush=True)
            print(f"  Panel items ({len(panel_full['items'])}):", flush=True)
            for item in panel_full['items']:
                vis = "" if item['vis'] else " [HIDDEN]"
                print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> .{item['class'][:35]} '{item['text'][:30]}'{vis}", flush=True)

        # Also check canvas area for audio timeline
        canvas_state = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var cls = (el.className || '').toString();
                var text = (el.innerText || '').trim();
                // Look specifically for audio/voice/timeline/upload elements
                if (r.width > 0 && (cls.includes('audio') || cls.includes('voice')
                    || cls.includes('timeline') || cls.includes('upload')
                    || cls.includes('record') || cls.includes('wav')
                    || cls.includes('mp3') || cls.includes('sound')
                    || text.includes('audio') || text.includes('Audio')
                    || text.includes('Upload') || text.includes('Record')
                    || text.includes('Voice') || text.includes('voice')
                    || text.includes('.mp3') || text.includes('.wav'))) {
                    items.push({
                        tag: el.tagName, class: cls.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 50),
                        visible: r.width > 5 && r.height > 5,
                    });
                }
            }
            return items;
        }""")
        print(f"\n  Audio-related elements ({len(canvas_state)}):", flush=True)
        for a in canvas_state:
            vis = "VISIBLE" if a['visible'] else "hidden"
            print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} [{vis}] <{a['tag']}> .{a['class'][:40]} '{a['text'][:30]}'", flush=True)

    ss(page, "P101_05_final")
    print(f"\n\n===== PHASE 101 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
