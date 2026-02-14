"""Phase 102: Complete Lip Sync face selection — target correct dialog thumbnails.
From P101 screenshots: "Pick Image" dialog centered, 3 canvas thumbs at x=450-740, y=390-480.
Previous code clicked (1189,674) = Results panel sidebar, NOT the dialog.
Fix: query inside .pick-image-dialog for images within dialog bounds.
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
    #  STEP 1: Open Lip Sync + Pick Face
    # ============================================================
    print("\n=== STEP 1: Open Lip Sync ===", flush=True)
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    is_open = page.evaluate("() => !!document.querySelector('.lip-sync-config-panel.show')")
    print(f"  Lip Sync open: {is_open}", flush=True)
    if not is_open:
        print("  ABORT", flush=True)
        os._exit(1)

    # Click "Pick a Face Image"
    print("\n=== STEP 2: Click Pick a Face Image ===", flush=True)
    coords = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button.pick-image')) {
            if (btn.classList.contains('pick-video')) continue;
            var r = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            if (text.includes('Face Image') && r.width > 100) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if coords:
        page.mouse.click(coords['x'], coords['y'])
        print(f"  Clicked at ({coords['x']},{coords['y']})", flush=True)
    else:
        print("  ABORT: no face image button", flush=True)
        os._exit(1)
    page.wait_for_timeout(3000)

    # ============================================================
    #  STEP 3: Map the EXACT .pick-image-dialog structure
    # ============================================================
    print("\n=== STEP 3: Map .pick-image-dialog ===", flush=True)

    dialog_dom = page.evaluate("""() => {
        var dialog = document.querySelector('.pick-image-dialog');
        if (!dialog) return {error: 'no .pick-image-dialog'};

        // Find the actual centered container (not the full-page overlay)
        var containers = [];
        for (var child of dialog.querySelectorAll('*')) {
            var r = child.getBoundingClientRect();
            // The dialog content is centered: roughly x=440-950, y=190-680
            if (r.width > 300 && r.width < 700 && r.height > 300 && r.height < 700
                && r.x > 300 && r.x < 600) {
                containers.push({
                    tag: child.tagName,
                    class: (child.className || '').toString().substring(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        // Find ALL images inside the dialog
        var images = [];
        for (var img of dialog.querySelectorAll('img')) {
            var r = img.getBoundingClientRect();
            if (r.width > 20 && r.height > 20) {
                images.push({
                    src: (img.src || '').substring(0, 120),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2),
                    cy: Math.round(r.y + r.height/2),
                    cursor: window.getComputedStyle(img).cursor,
                    parentTag: img.parentElement?.tagName,
                    parentClass: (img.parentElement?.className || '').toString().substring(0, 60),
                    parentCursor: window.getComputedStyle(img.parentElement).cursor,
                });
            }
        }

        // Find clickable divs with background-image inside dialog
        var bgDivs = [];
        for (var el of dialog.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            var bg = cs.backgroundImage || '';
            if (r.width > 50 && r.height > 50 && bg !== 'none' && bg !== ''
                && r.x > 400 && r.x < 800 && r.y > 350 && r.y < 500) {
                bgDivs.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2),
                    cy: Math.round(r.y + r.height/2),
                    bg: bg.substring(0, 120),
                    cursor: cs.cursor,
                });
            }
        }

        return {containers: containers, images: images, bgDivs: bgDivs};
    }""")

    print(f"\n  Containers ({len(dialog_dom.get('containers', []))}):", flush=True)
    for c in dialog_dom.get('containers', []):
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> .{c['class'][:60]}", flush=True)

    print(f"\n  Images ({len(dialog_dom.get('images', []))}):", flush=True)
    for img in dialog_dom.get('images', []):
        pcur = f" pCur={img['parentCursor']}" if img.get('parentCursor') != 'auto' else ""
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} center=({img['cx']},{img['cy']}) cur={img['cursor']}{pcur}", flush=True)
        print(f"      p=<{img['parentTag']}>.{img['parentClass'][:40]}", flush=True)
        print(f"      src={img['src'][:80]}", flush=True)

    print(f"\n  BG divs ({len(dialog_dom.get('bgDivs', []))}):", flush=True)
    for d in dialog_dom.get('bgDivs', []):
        print(f"    ({d['x']},{d['y']}) {d['w']}x{d['h']} center=({d['cx']},{d['cy']}) cur={d['cursor']}", flush=True)
        print(f"      <{d['tag']}>.{d['class'][:40]}", flush=True)
        print(f"      bg={d['bg'][:80]}", flush=True)

    # ============================================================
    #  STEP 4: Click the FIRST canvas thumbnail in the dialog
    # ============================================================
    print("\n=== STEP 4: Click canvas thumbnail ===", flush=True)

    # From screenshot: thumbnails are at y~390-480, x~450-740, inside the dialog
    # They might be <img> or divs with background-image
    thumb = page.evaluate("""() => {
        var dialog = document.querySelector('.pick-image-dialog');
        if (!dialog) return null;

        // Strategy A: find img elements in the dialog between x=400-800, y=350-500
        for (var img of dialog.querySelectorAll('img')) {
            var r = img.getBoundingClientRect();
            if (r.width > 50 && r.height > 50 && r.x > 400 && r.x < 800
                && r.y > 350 && r.y < 500) {
                return {
                    strategy: 'img-in-dialog',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    src: (img.src || '').substring(0, 100),
                };
            }
        }

        // Strategy B: find divs with background-image in dialog area
        for (var el of dialog.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            var bg = cs.backgroundImage || '';
            if (r.width > 50 && r.height > 50 && bg !== 'none' && bg !== ''
                && r.x > 400 && r.x < 800 && r.y > 350 && r.y < 500) {
                return {
                    strategy: 'bg-div-in-dialog',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    bg: bg.substring(0, 100),
                };
            }
        }

        // Strategy C: find any clickable element in the thumbnail area
        for (var el of dialog.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            if (r.width > 50 && r.height > 50 && r.width < 200
                && r.x > 400 && r.x < 800 && r.y > 370 && r.y < 500
                && cs.cursor === 'pointer') {
                return {
                    strategy: 'pointer-cursor',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                };
            }
        }

        return null;
    }""")

    if thumb:
        print(f"  Strategy: {thumb['strategy']}", flush=True)
        print(f"  Clicking at ({thumb['x']},{thumb['y']}) {thumb['w']}x{thumb['h']}", flush=True)
        for k in ('src', 'bg', 'class'):
            if k in thumb:
                print(f"    {k}: {thumb[k]}", flush=True)

        page.mouse.click(thumb['x'], thumb['y'])
        page.wait_for_timeout(4000)
        ss(page, "P102_01_after_thumb_click")
    else:
        print("  No thumbnail found via DOM! Trying direct mouse click from screenshot coords", flush=True)
        # From screenshot: first thumbnail center is approximately (490, 435)
        page.mouse.click(490, 435)
        page.wait_for_timeout(4000)
        ss(page, "P102_01_mouse_click_490_435")

    # ============================================================
    #  STEP 5: Check what happened — face detect dialog?
    # ============================================================
    print("\n=== STEP 5: Check for face detection ===", flush=True)

    state = page.evaluate("""() => {
        // Check for edit-image-dialog (face detection)
        var eid = document.querySelector('.edit-image-dialog');
        if (eid) {
            var r = eid.getBoundingClientRect();
            return {
                state: 'face-detect-dialog',
                class: (eid.className || '').toString(),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (eid.innerText || '').substring(0, 200),
            };
        }

        // Check for face-related text
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.includes('face selected') || t === 'Mark Face Manually'
                || t.includes('Pick a Face')) {
                var r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 10) {
                    return {state: 'face-text', text: t.substring(0, 100),
                            x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
        }

        // Check if pick dialog is still open
        var pd = document.querySelector('.pick-image-dialog');
        if (pd) {
            var r = pd.getBoundingClientRect();
            if (r.width > 0) {
                return {state: 'pick-dialog-still-open',
                        text: (pd.innerText || '').substring(0, 200)};
            }
        }

        return {state: 'unknown'};
    }""")
    print(f"  State: {json.dumps(state, indent=2)}", flush=True)

    # ============================================================
    #  STEP 6: If face detect → Next → Crop → Next → Check panel
    # ============================================================
    if state.get('state') in ('face-detect-dialog', 'face-text'):
        print("\n=== STEP 6: Face detect → crop → done ===", flush=True)
        ss(page, "P102_02_face_detect")

        # Click Next (face → crop)
        print("  Next 1: face → crop...", flush=True)
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Next') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        ss(page, "P102_03_crop")

        # Click Next (crop → done)
        print("  Next 2: crop → done...", flush=True)
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Next') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(5000)
        close_dialogs(page)
        ss(page, "P102_04_after_crop")

        # ============================================================
        #  STEP 7: Check panel state — face set? Audio upload?
        # ============================================================
        print("\n=== STEP 7: Panel state after face set ===", flush=True)

        panel_state = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return {error: 'no panel'};

            var warning = (p.innerText || '').includes('Please pick');
            var fullText = (p.innerText || '').trim();

            // Check for face preview image
            var faceImg = null;
            for (var img of p.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.width > 20 && r.height > 20) {
                    faceImg = {
                        src: (img.src || '').substring(0, 120),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                }
            }

            // Map ALL visible panel items
            var items = [];
            var seen = new Set();
            for (var child of p.querySelectorAll('*')) {
                var r = child.getBoundingClientRect();
                if (r.width < 3 || r.height < 3) continue;
                var text = (child.innerText || '').trim();
                var cls = (child.className || '').toString();
                var tag = child.tagName;
                var key = tag + '|' + Math.round(r.y/5) + '|' + text.substring(0,10);
                if (seen.has(key)) continue;
                seen.add(key);
                if (text.length > 0 || tag === 'IMG' || tag === 'BUTTON' || tag === 'INPUT'
                    || cls.includes('audio') || cls.includes('voice')
                    || cls.includes('upload') || cls.includes('face')
                    || cls.includes('preview')) {
                    items.push({
                        tag: tag, class: cls.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 60),
                    });
                }
            }
            items.sort(function(a,b){return a.y - b.y});

            return {warning: warning, faceImg: faceImg, fullText: fullText.substring(0, 500),
                    items: items.slice(0, 50)};
        }""")

        if panel_state:
            print(f"  Warning: {panel_state.get('warning')}", flush=True)
            print(f"  Face img: {panel_state.get('faceImg')}", flush=True)
            print(f"  Full text: {panel_state['fullText'][:200]}", flush=True)
            print(f"\n  Panel items ({len(panel_state.get('items', []))}):", flush=True)
            for item in panel_state.get('items', [])[:35]:
                print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> .{item['class'][:30]} '{item['text'][:40]}'", flush=True)

        # Check canvas area for audio-related elements
        print("\n  Checking canvas for audio UI...", flush=True)
        audio_check = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var cls = (el.className || '').toString();
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if ((cls.includes('audio') || cls.includes('voice') || cls.includes('timeline')
                    || cls.includes('upload') || cls.includes('record')
                    || cls.includes('pick-voice') || cls.includes('sound')
                    || text.includes('Upload') || text.includes('Audio')
                    || text.includes('Voice') || text.includes('Record')
                    || text.includes('Browse')) && r.width > 0) {
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
        print(f"  Audio elements ({len(audio_check)}):", flush=True)
        for a in audio_check:
            vis = "VIS" if a['visible'] else "hid"
            print(f"    [{vis}] ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> .{a['class'][:40]} '{a['text'][:30]}'", flush=True)

        # Check entire lip-sync panel area (canvas part)
        print("\n  Lip Sync canvas area elements...", flush=True)
        ls_canvas = page.evaluate("""() => {
            var panel = document.querySelector('.lip-sync-config-panel.show');
            if (!panel) return [];
            var items = [];
            var seen = new Set();
            for (var child of panel.querySelectorAll('*')) {
                var r = child.getBoundingClientRect();
                if (r.width < 10 || r.height < 10) continue;
                // Canvas area: x > 350 (right of config panel)
                if (r.x < 350) continue;
                var text = (child.innerText || '').trim();
                var cls = (child.className || '').toString();
                var tag = child.tagName;
                var key = tag + '|' + Math.round(r.y/5) + '|' + Math.round(r.x/5);
                if (seen.has(key)) continue;
                seen.add(key);
                if (r.width > 30 && r.height > 15) {
                    items.push({
                        tag: tag, class: cls.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 40),
                    });
                }
            }
            items.sort(function(a,b){return a.y - b.y});
            return items.slice(0, 30);
        }""")
        print(f"  Canvas items ({len(ls_canvas)}):", flush=True)
        for c in ls_canvas:
            print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> .{c['class'][:30]} '{c['text'][:30]}'", flush=True)

    else:
        print(f"  Face detect not found. State: {state.get('state')}", flush=True)
        # If pick dialog still open, screenshot it again
        if state.get('state') == 'pick-dialog-still-open':
            print("  Dialog still open — thumbnail click didn't work", flush=True)

    ss(page, "P102_05_final")
    print(f"\n\n===== PHASE 102 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
