"""Phase 91: Lip Sync workflow exploration.
Goal: Understand how to automate Lip Sync for Ray videos.
1. Open Lip Sync panel
2. Explore the "Pick a face" dialog
3. Understand audio upload mechanism
4. Map all available selectors for automation
5. Also: fix result image URL detection from Phase 90
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


def open_panel(page, target_x, target_y, panel_name=""):
    page.mouse.click(40, 766)  # Storyboard
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(500)
    page.mouse.click(target_x, target_y)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)


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
    #  PART 1: RESULT IMAGE URL DETECTION FIX
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: RESULT IMAGE URLS", flush=True)
    print("=" * 60, flush=True)

    # Find ALL image URLs on the page to understand URL patterns
    all_imgs = page.evaluate("""() => {
        var imgs = [];
        var seen = new Set();
        for (var img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src && !seen.has(src) && src.length > 10 && !src.startsWith('data:')) {
                seen.add(src);
                var r = img.getBoundingClientRect();
                imgs.push({
                    src: src.substring(0, 120),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.width > 0 && r.height > 0,
                });
            }
        }
        // Also check background-image CSS
        var bgImgs = [];
        for (var el of document.querySelectorAll('.result-image, [class*="result"], [class*="thumbnail"]')) {
            var cs = window.getComputedStyle(el);
            var bg = cs.backgroundImage;
            if (bg && bg !== 'none') {
                var r = el.getBoundingClientRect();
                bgImgs.push({
                    bg: bg.substring(0, 120),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return {imgs: imgs, bgImgs: bgImgs};
    }""")
    print(f"\n  IMG elements ({len(all_imgs.get('imgs', []))}):", flush=True)
    for img in all_imgs.get('imgs', []):
        vis = " VISIBLE" if img['visible'] else ""
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']}{vis} {img['src']}", flush=True)
    print(f"\n  BG images ({len(all_imgs.get('bgImgs', []))}):", flush=True)
    for bg in all_imgs.get('bgImgs', []):
        print(f"    ({bg['x']},{bg['y']}) {bg['w']}x{bg['h']} c='{bg['classes']}' bg={bg['bg'][:80]}", flush=True)

    # Check for canvas-based images (Konva.js)
    canvas_check = page.evaluate("""() => {
        var canvases = document.querySelectorAll('canvas');
        var results = [];
        for (var c of canvases) {
            var r = c.getBoundingClientRect();
            results.push({
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                id: c.id || '',
                classes: (c.className || '').toString().substring(0, 30),
            });
        }
        return results;
    }""")
    print(f"\n  Canvas elements ({len(canvas_check)}):", flush=True)
    for c in canvas_check:
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} id='{c['id']}' c='{c['classes']}'", flush=True)

    # ============================================================
    #  PART 2: LIP SYNC — PANEL + PICK FACE DIALOG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: LIP SYNC PANEL", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    open_panel(page, 40, 425, "Lip Sync")
    ss(page, "P91_01_lip_sync")

    # Now explore the "Pick a face" interaction
    # The warning says "Please pick a face image or video"
    # There should be an upload area at the top of the panel
    ls_uploads = page.evaluate("""() => {
        var panel = document.querySelector('.lip-sync-operation-panel') ||
                    document.querySelector('.c-gen-config.show');
        if (!panel) return null;

        var items = [];
        for (var child of panel.querySelectorAll('*')) {
            var cls = (child.className || '').toString();
            var r = child.getBoundingClientRect();
            // Look for upload areas, pickers, drop zones
            if (cls.includes('upload') || cls.includes('pick') || cls.includes('drop')
                || cls.includes('drag') || cls.includes('face') || cls.includes('video')
                || child.tagName === 'INPUT') {
                items.push({
                    tag: child.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: cls.substring(0, 40),
                    type: child.type || '',
                    text: (child.innerText || '').trim().substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Lip Sync upload elements ({len(ls_uploads) if ls_uploads else 0}):", flush=True)
    if ls_uploads:
        for u in ls_uploads:
            tp = f" type={u['type']}" if u['type'] else ''
            print(f"    ({u['x']},{u['y']}) {u['w']}x{u['h']} <{u['tag']}> c='{u['classes'][:30]}' '{u['text'][:25]}'{tp}", flush=True)

    # The Lip Sync might need a canvas image selected first
    # Let's check if there's a "pick from canvas" option
    # Click in the face area at the top of the panel
    page.evaluate("""() => {
        var panel = document.querySelector('.lip-sync-operation-panel');
        if (!panel) return;
        // Look for the face picker area (should be before "Generation Mode" text)
        var btns = panel.querySelectorAll('button');
        for (var btn of btns) {
            var text = (btn.innerText || '').trim();
            if (text.includes('pick') || text.includes('upload') || text.includes('face')) {
                btn.click(); return 'clicked: ' + text;
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # Also try clicking where the face preview would be
    # Based on the panel structure, the face area would be between header and Generation Mode
    # Header is at y=73, Generation Mode label at y=117
    # So the face area might be hidden or is the space that says "pick a face"

    # Check the full panel HTML structure
    panel_html = page.evaluate("""() => {
        var panel = document.querySelector('.lip-sync-operation-panel');
        if (!panel) return null;
        // Get all direct children structure
        var children = [];
        for (var child of panel.children) {
            var r = child.getBoundingClientRect();
            children.push({
                tag: child.tagName,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                classes: (child.className || '').toString().substring(0, 40),
                text: (child.innerText || '').trim().substring(0, 60),
                childCount: child.children.length,
            });
        }
        return children;
    }""")
    print(f"\n  Panel children ({len(panel_html) if panel_html else 0}):", flush=True)
    if panel_html:
        for ch in panel_html:
            print(f"    ({ch['x']},{ch['y']}) {ch['w']}x{ch['h']} <{ch['tag']}> c='{ch['classes'][:30]}' ch={ch['childCount']} '{ch['text'][:40]}'", flush=True)

    # ============================================================
    #  PART 3: LIP SYNC — FROM RESULT PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: LIP SYNC FROM RESULTS", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.evaluate("() => document.querySelector('.header-item.item-results')?.click()")
    page.wait_for_timeout(1000)

    # In the Results panel, each result has a "Lip Sync" action button
    # Find and click it for the latest result
    ls_from_result = page.evaluate("""() => {
        // Find the Lip Sync button in the results panel
        var panel = document.querySelector('.c-material-library-v2');
        if (!panel) return 'no panel';
        var items = [];
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Lip Sync' && r.height < 30 && r.width < 200 && r.x > 1050) {
                items.push({
                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return items;
    }""")
    print(f"  Lip Sync buttons in results: {ls_from_result}", flush=True)

    # Find the "1" button for the first Lip Sync row
    if isinstance(ls_from_result, list) and ls_from_result:
        first_ls = ls_from_result[0]
        # The "1" button should be to the right of the label
        btn_y = first_ls['y']
        page.evaluate(f"""() => {{
            var panel = document.querySelector('.c-material-library-v2');
            if (!panel) return;
            for (var btn of panel.querySelectorAll('button.btn')) {{
                var r = btn.getBoundingClientRect();
                if (Math.abs(r.y - {btn_y}) < 10 && (btn.innerText || '').trim() === '1') {{
                    btn.click(); return;
                }}
            }}
        }}""")
        page.wait_for_timeout(3000)
        close_dialogs(page)
        dismiss_popups(page)
        ss(page, "P91_02_ls_from_result")

        # Check what happened — did a Lip Sync dialog/panel open?
        ls_dialog = page.evaluate("""() => {
            var items = [];
            var seen = new Set();
            // Check for high-z overlays
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 500 && r.width > 200 && r.height > 100) {
                    for (var child of el.querySelectorAll('*')) {
                        var cr = child.getBoundingClientRect();
                        var text = (child.innerText || '').trim();
                        if (text.length > 0 && text.length < 50 && cr.width > 10
                            && cr.height > 8 && cr.height < 50 && cr.width < 300
                            && text.indexOf('\\n') === -1) {
                            var key = text + '|' + Math.round(cr.y);
                            if (!seen.has(key)) {
                                seen.add(key);
                                items.push({
                                    tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                                    w: Math.round(cr.width), h: Math.round(cr.height),
                                    text: text.substring(0, 40),
                                    classes: (child.className || '').toString().substring(0, 30),
                                    z: z,
                                });
                            }
                        }
                    }
                    break;
                }
            }
            // Also check for lip-sync panel
            var lsp = document.querySelector('.lip-sync-operation-panel');
            var lspInfo = null;
            if (lsp) {
                var r = lsp.getBoundingClientRect();
                lspInfo = {x: Math.round(r.x), y: Math.round(r.y),
                           w: Math.round(r.width), h: Math.round(r.height)};
            }
            return {overlay: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20), lsp: lspInfo};
        }""")
        print(f"\n  Lip Sync dialog:", flush=True)
        print(f"    Panel: {ls_dialog.get('lsp')}", flush=True)
        print(f"    Overlay ({len(ls_dialog.get('overlay', []))}):", flush=True)
        for o in ls_dialog.get('overlay', []):
            print(f"      ({o['x']},{o['y']}) {o['w']}x{o['h']} z={o['z']} <{o['tag']}> c='{o['classes'][:22]}' '{o['text']}'", flush=True)

    # ============================================================
    #  PART 4: AUDIO UPLOAD FOR LIP SYNC
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: AUDIO UPLOAD MECHANISM", flush=True)
    print("=" * 60, flush=True)

    # The Lip Sync needs: 1) face image, 2) audio
    # After clicking Lip Sync from results, the face is auto-selected
    # Now we need to find the audio upload mechanism

    # Check for audio-related elements
    audio_els = page.evaluate("""() => {
        var items = [];
        var selectors = [
            '[class*="audio"]', '[class*="voice"]', '[class*="mp3"]',
            '[class*="wav"]', '[class*="sound"]', 'input[type="file"]',
            'input[accept*="audio"]', '[class*="upload"]',
        ];
        for (var sel of selectors) {
            var els = document.querySelectorAll(sel);
            for (var el of els) {
                var r = el.getBoundingClientRect();
                items.push({
                    sel: sel,
                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                    text: (el.innerText || '').trim().substring(0, 40),
                    type: el.type || '',
                    accept: el.accept || '',
                });
            }
        }
        return items;
    }""")
    print(f"\n  Audio elements ({len(audio_els)}):", flush=True)
    for a in audio_els:
        print(f"    {a['sel']} <{a['tag']}> ({a['x']},{a['y']}) {a['w']}x{a['h']} "
              f"c='{a['classes'][:25]}' type={a['type']} accept={a['accept']} '{a['text'][:25]}'", flush=True)

    # Also find ALL file input elements
    file_inputs = page.evaluate("""() => {
        var inputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            inputs.push({
                x: Math.round(inp.getBoundingClientRect().x),
                y: Math.round(inp.getBoundingClientRect().y),
                accept: inp.accept || 'any',
                classes: (inp.className || '').toString().substring(0, 30),
                id: inp.id || '',
                name: inp.name || '',
            });
        }
        return inputs;
    }""")
    print(f"\n  File inputs ({len(file_inputs)}):", flush=True)
    for f in file_inputs:
        print(f"    ({f['x']},{f['y']}) accept='{f['accept']}' id='{f['id']}' name='{f['name']}' c='{f['classes']}'", flush=True)

    # ============================================================
    #  PART 5: RESULT IMAGE DOWNLOAD MECHANISM
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: RESULT IMAGE DOWNLOAD", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results panel and examine the result image structure
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.evaluate("() => document.querySelector('.header-item.item-results')?.click()")
    page.wait_for_timeout(1000)

    # Look at the result section structure
    results_detail = page.evaluate("""() => {
        var panel = document.querySelector('.c-material-library-v2');
        if (!panel) return null;

        // Find result sections
        var sections = [];
        for (var el of panel.querySelectorAll('[class*="result"], .group-section, .result-section')) {
            var r = el.getBoundingClientRect();
            if (r.width > 100 && r.height > 50) {
                sections.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 50),
                    children: el.children.length,
                });
            }
        }

        // Find all images in the results area
        var images = [];
        for (var img of panel.querySelectorAll('img')) {
            var src = img.src || '';
            var r = img.getBoundingClientRect();
            if (r.width > 10 && r.height > 10) {
                images.push({
                    src: src.substring(0, 120),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        // Check for bg images in result thumbnails
        var bgImgs = [];
        for (var el of panel.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var bg = cs.backgroundImage;
            if (bg && bg !== 'none' && bg.includes('url(')) {
                var r = el.getBoundingClientRect();
                if (r.width > 30 && r.height > 30) {
                    bgImgs.push({
                        bg: bg.substring(4, 124).replace(')', ''),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }

        return {sections: sections.slice(0, 10), images: images.slice(0, 10), bgImgs: bgImgs.slice(0, 10)};
    }""")
    if results_detail:
        print(f"\n  Result sections ({len(results_detail.get('sections', []))}):", flush=True)
        for s in results_detail.get('sections', []):
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> ch={s['children']} c='{s['classes'][:40]}'", flush=True)
        print(f"\n  Result images ({len(results_detail.get('images', []))}):", flush=True)
        for img in results_detail.get('images', []):
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src']}", flush=True)
        print(f"\n  Result bg images ({len(results_detail.get('bgImgs', []))}):", flush=True)
        for bg in results_detail.get('bgImgs', []):
            print(f"    ({bg['x']},{bg['y']}) {bg['w']}x{bg['h']} c='{bg['classes']}' {bg['bg'][:80]}", flush=True)

    print(f"\n\n===== PHASE 91 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
