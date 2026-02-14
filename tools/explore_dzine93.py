"""Phase 93: Lip Sync COMPLETE WORKFLOW + Img2Img.
Focus:
A) Lip Sync: Results panel → action button → Pick Face → Next → Audio step
B) Img2Img: Direct open, full panel mapping, upload mechanism
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
    #  PART A: LIP SYNC VIA RESULTS PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART A: LIP SYNC FROM RESULTS", flush=True)
    print("=" * 60, flush=True)

    # A1: Switch to Results tab
    print("\n  A1: Opening Results panel...", flush=True)
    page.evaluate("() => document.querySelector('.header-item.item-results')?.click()")
    page.wait_for_timeout(1000)

    # Scroll results to top
    page.evaluate("""() => {
        var panel = document.querySelector('.c-material-library-v2');
        if (panel) {
            var scroll = panel.querySelector('.material-v2-result-content, [class*="result-content"]');
            if (scroll) scroll.scrollTop = 0;
        }
    }""")
    page.wait_for_timeout(500)

    # A2: Find the first "Lip Sync" action button with its clickable "1" button
    print("  A2: Finding Lip Sync action on first result...", flush=True)

    # The results panel has actions for each result group.
    # Each action row has: label + "1" button + "2" button
    # We need to find the Lip Sync row and click "1" (first image)
    lip_sync_btn = page.evaluate("""() => {
        var panel = document.querySelector('.c-material-library-v2');
        if (!panel) return 'no panel';

        // Find all action rows
        var allLabels = [];
        for (var el of panel.querySelectorAll('.label-text')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.y > 0 && r.y < 900) {
                allLabels.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        // Find visible Lip Sync label
        for (var label of allLabels) {
            if (label.text === 'Lip Sync' && label.y > 0 && label.y < 800) {
                // Find the "1" button near this label (same row, slightly to the right)
                for (var btn of panel.querySelectorAll('button.btn, .label button')) {
                    var br = btn.getBoundingClientRect();
                    var bt = (btn.innerText || '').trim();
                    if (bt === '1' && Math.abs(br.y - label.y) < 15 && br.x > label.x) {
                        btn.click();
                        return 'clicked 1 for Lip Sync at y=' + label.y;
                    }
                }
                // Try clicking the label-text area itself
                return {found: label, labels: allLabels.slice(0, 15)};
            }
        }
        return {labels: allLabels.slice(0, 15)};
    }""")
    print(f"  Lip Sync btn: {lip_sync_btn}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    ss(page, "P93_01_results_lip_sync")

    # A3: Check if "Pick a Face" dialog opened
    print("\n  A3: Checking for Pick a Face dialog...", flush=True)
    face_dialog = page.evaluate("""() => {
        // Look for high-z overlay with "Pick a Face" title
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 300 && r.height > 200) {
                var title = '';
                for (var h of el.querySelectorAll('h2, h3, [class*="title"], [class*="header"]')) {
                    var ht = (h.innerText || '').trim();
                    if (ht.length > 0 && ht.length < 30) {
                        title = ht;
                        break;
                    }
                }

                // Check for "Next" button
                var hasNext = false;
                for (var btn of el.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === 'Next') hasNext = true;
                }

                // Check for face count
                var faceStatus = '';
                for (var txt of el.querySelectorAll('*')) {
                    var t = (txt.innerText || '').trim();
                    if (t.includes('face selected') || t.includes('Up to')) {
                        faceStatus = t;
                        break;
                    }
                }

                return {
                    title: title, z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    hasNext: hasNext,
                    faceStatus: faceStatus,
                    classes: (el.className || '').toString().substring(0, 60),
                };
            }
        }
        return null;
    }""")
    print(f"  Face dialog: {face_dialog}", flush=True)

    if face_dialog and face_dialog.get('hasNext'):
        # A4: Face is auto-selected — click Next
        print("\n  A4: Clicking Next...", flush=True)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                if (z > 500) {
                    for (var btn of el.querySelectorAll('button')) {
                        if ((btn.innerText || '').trim() === 'Next') {
                            btn.click();
                            return;
                        }
                    }
                }
            }
        }""")
        page.wait_for_timeout(3000)
        close_dialogs(page)
        ss(page, "P93_02_after_next")

        # A5: Map what we see now — should be audio upload step
        print("\n  A5: Mapping audio step...", flush=True)
        audio_step = page.evaluate("""() => {
            var result = {overlays: [], panel: null, fileInputs: []};

            // Check high-z overlays
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 500 && r.width > 200 && r.height > 100) {
                    var children = [];
                    var seen = new Set();
                    for (var child of el.querySelectorAll('*')) {
                        var cr = child.getBoundingClientRect();
                        var text = (child.innerText || '').trim();
                        var ctag = child.tagName;
                        if (cr.width > 0 && cr.height > 0
                            && (ctag === 'BUTTON' || ctag === 'INPUT' || ctag === 'TEXTAREA'
                                || (text.length > 0 && text.length < 80
                                    && text.indexOf('\\n') === -1
                                    && cr.height < 80 && cr.width < 500))) {
                            var key = text.substring(0,20) + '|' + Math.round(cr.y) + '|' + ctag;
                            if (!seen.has(key)) {
                                seen.add(key);
                                children.push({
                                    tag: ctag,
                                    x: Math.round(cr.x), y: Math.round(cr.y),
                                    w: Math.round(cr.width), h: Math.round(cr.height),
                                    text: text.substring(0, 60),
                                    classes: (child.className || '').toString().substring(0, 40),
                                    type: child.type || '',
                                    accept: child.accept || '',
                                });
                            }
                        }
                    }
                    result.overlays.push({
                        z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 60),
                        children: children.sort(function(a,b) { return a.y - b.y; }),
                    });
                    break;
                }
            }

            // Check Lip Sync panel
            var lsp = document.querySelector('.c-gen-config.show');
            if (lsp) {
                var lr = lsp.getBoundingClientRect();
                result.panel = {
                    x: Math.round(lr.x), y: Math.round(lr.y),
                    w: Math.round(lr.width), h: Math.round(lr.height),
                    text: (lsp.innerText || '').trim().substring(0, 300),
                    classes: (lsp.className || '').toString().substring(0, 60),
                };
            }

            // All file inputs globally
            for (var inp of document.querySelectorAll('input[type="file"]')) {
                result.fileInputs.push({
                    accept: inp.accept || 'any',
                    classes: (inp.className || '').toString().substring(0, 30),
                    id: inp.id || '',
                });
            }

            return result;
        }""")

        print(f"\n  Overlays ({len(audio_step.get('overlays', []))}):", flush=True)
        for ov in audio_step.get('overlays', []):
            print(f"  [OVERLAY] z={ov['z']} ({ov['x']},{ov['y']}) {ov['w']}x{ov['h']} c='{ov['classes'][:45]}'", flush=True)
            for ch in ov.get('children', [])[:25]:
                extra = ""
                if ch.get('type'):
                    extra += f" type={ch['type']}"
                if ch.get('accept'):
                    extra += f" accept={ch['accept']}"
                print(f"    ({ch['x']},{ch['y']}) {ch['w']}x{ch['h']} <{ch['tag']}> c='{ch['classes'][:25]}' '{ch['text'][:45]}'{extra}", flush=True)

        if audio_step.get('panel'):
            p = audio_step['panel']
            print(f"\n  [PANEL] ({p['x']},{p['y']}) {p['w']}x{p['h']} c='{p['classes'][:45]}'", flush=True)
            print(f"    text: {p['text'][:200]}", flush=True)

        print(f"\n  File inputs ({len(audio_step.get('fileInputs', []))}):", flush=True)
        for fi in audio_step.get('fileInputs', []):
            print(f"    accept='{fi['accept']}' id='{fi['id']}' c='{fi['classes']}'", flush=True)

    elif not face_dialog:
        # Face dialog didn't open — try alternative: click on a result image first
        print("\n  No face dialog. Trying to click on result thumbnail first...", flush=True)

        # Click the first visible result image in the panel
        clicked_result = page.evaluate("""() => {
            var panel = document.querySelector('.c-material-library-v2');
            if (!panel) return 'no panel';
            var imgs = panel.querySelectorAll('img');
            for (var img of imgs) {
                var src = img.src || '';
                var r = img.getBoundingClientRect();
                if (src.includes('stylar_product') && r.width > 50 && r.y > 0 && r.y < 400) {
                    img.click();
                    return 'clicked img at (' + Math.round(r.x) + ',' + Math.round(r.y) + ') ' + src.substring(0, 80);
                }
            }
            return 'no images found';
        }""")
        print(f"  Click result: {clicked_result}", flush=True)
        page.wait_for_timeout(2000)
        ss(page, "P93_01b_result_clicked")

        # Now check for action buttons on the selected result
        actions = page.evaluate("""() => {
            var panel = document.querySelector('.c-material-library-v2');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('.label, .label-text, button.btn')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.y > 0 && r.y < 500 && r.width > 0 && text.length > 0 && text.length < 30) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        classes: (el.className || '').toString().substring(0, 30),
                        tag: el.tagName,
                    });
                }
            }
            return items;
        }""")
        print(f"\n  Visible action buttons ({len(actions)}):", flush=True)
        for a in actions[:20]:
            print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> '{a['text']}' c='{a['classes'][:25]}'", flush=True)

        # Try to find and click the "1" button next to "Lip Sync"
        ls_clicked = page.evaluate("""() => {
            var panel = document.querySelector('.c-material-library-v2');
            if (!panel) return 'no panel';

            // Find Lip Sync label rows
            var rows = panel.querySelectorAll('.label');
            for (var row of rows) {
                var labelText = row.querySelector('.label-text');
                if (!labelText) continue;
                var lt = (labelText.innerText || '').trim();
                if (lt !== 'Lip Sync') continue;

                var rr = row.getBoundingClientRect();
                if (rr.y < 0 || rr.y > 800) continue;

                // Find "1" button in this row
                for (var btn of row.querySelectorAll('button')) {
                    var bt = (btn.innerText || '').trim();
                    if (bt === '1') {
                        btn.click();
                        return 'clicked Lip Sync 1 at y=' + Math.round(rr.y);
                    }
                }
                // Try clicking the row itself
                row.click();
                return 'clicked Lip Sync row at y=' + Math.round(rr.y);
            }
            return 'Lip Sync row not found';
        }""")
        print(f"\n  Lip Sync click: {ls_clicked}", flush=True)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        ss(page, "P93_02b_lip_sync_clicked")

        # Check for face dialog again
        face_dialog2 = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 500 && r.width > 300 && r.height > 200) {
                    return {
                        z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').trim().substring(0, 200),
                    };
                }
            }
            return null;
        }""")
        print(f"\n  Face dialog: {face_dialog2}", flush=True)

        if face_dialog2:
            # Click Next in the face dialog
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var cs = window.getComputedStyle(el);
                    var z = parseInt(cs.zIndex) || 0;
                    if (z > 500) {
                        for (var btn of el.querySelectorAll('button')) {
                            if ((btn.innerText || '').trim() === 'Next') {
                                btn.click();
                                return;
                            }
                        }
                    }
                }
            }""")
            page.wait_for_timeout(3000)
            close_dialogs(page)
            ss(page, "P93_03_after_next")

            # Map audio step
            audio_info = page.evaluate("""() => {
                var items = [];
                // High-z overlay
                for (var el of document.querySelectorAll('*')) {
                    var cs = window.getComputedStyle(el);
                    var z = parseInt(cs.zIndex) || 0;
                    var r = el.getBoundingClientRect();
                    if (z > 500 && r.width > 200 && r.height > 100) {
                        var seen = new Set();
                        for (var child of el.querySelectorAll('*')) {
                            var cr = child.getBoundingClientRect();
                            var text = (child.innerText || '').trim();
                            var ctag = child.tagName;
                            if (cr.width > 0 && cr.height > 0
                                && (ctag === 'BUTTON' || ctag === 'INPUT'
                                    || (text.length > 0 && text.length < 80
                                        && text.indexOf('\\n') === -1
                                        && cr.height < 80))) {
                                var key = text.substring(0,20) + '|' + Math.round(cr.y);
                                if (!seen.has(key)) {
                                    seen.add(key);
                                    items.push({
                                        tag: ctag,
                                        x: Math.round(cr.x), y: Math.round(cr.y),
                                        w: Math.round(cr.width), h: Math.round(cr.height),
                                        text: text.substring(0, 60),
                                        type: child.type || '',
                                        accept: child.accept || '',
                                    });
                                }
                            }
                        }
                        break;
                    }
                }
                // Also check panel
                var p = document.querySelector('.c-gen-config.show');
                if (p) {
                    items.push({
                        tag: 'PANEL',
                        x: 0, y: 0, w: 0, h: 0,
                        text: (p.innerText || '').trim().substring(0, 300),
                        type: '', accept: '',
                    });
                }
                return items;
            }""")
            print(f"\n  Audio step elements ({len(audio_info)}):", flush=True)
            for a in audio_info[:30]:
                extra = ""
                if a.get('type'): extra += f" type={a['type']}"
                if a.get('accept'): extra += f" accept={a['accept']}"
                if a['tag'] == 'PANEL':
                    print(f"  [PANEL] {a['text'][:200]}", flush=True)
                else:
                    print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> '{a['text'][:45]}'{extra}", flush=True)

    # ============================================================
    #  PART B: IMG2IMG PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART B: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    # Close overlays gently (just Escape, no click away)
    for _ in range(5):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.wait_for_timeout(1000)

    # B1: Click Img2Img directly in the left toolbar
    print("  B1: Clicking Img2Img...", flush=True)
    page.mouse.click(37, 240)  # Img2Img position
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Check what panel opened
    panel_class = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        return {
            classes: (p.className || '').toString(),
            x: Math.round(p.getBoundingClientRect().x),
            y: Math.round(p.getBoundingClientRect().y),
            w: Math.round(p.getBoundingClientRect().width),
            h: Math.round(p.getBoundingClientRect().height),
            title: '',
        };
    }""")
    print(f"  Panel: {panel_class}", flush=True)

    if not panel_class or 'img2img' not in (panel_class.get('classes', '') if panel_class else ''):
        # Not Img2Img — try toggling
        print("  Panel not Img2Img, toggling...", flush=True)
        page.mouse.click(37, 750)  # Storyboard
        page.wait_for_timeout(2000)
        close_dialogs(page)
        page.mouse.move(700, 450)
        page.wait_for_timeout(500)
        page.mouse.click(37, 240)  # Img2Img
        page.wait_for_timeout(3000)
        close_dialogs(page)
        dismiss_popups(page)

        panel_class = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return null;
            return (p.className || '').toString();
        }""")
        print(f"  Panel after toggle: {panel_class}", flush=True)

    ss(page, "P93_04_img2img")

    # B2: Full Img2Img panel mapping
    print("\n  B2: Full Img2Img mapping...", flush=True)
    i2i_full = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;

        var items = [];
        var seen = new Set();

        for (var child of panel.querySelectorAll('*')) {
            var r = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            var cls = (child.className || '').toString();
            var tag = child.tagName;

            if (r.width > 0 && r.height > 0 && r.height < 100
                && text.length > 0 && text.length < 60
                && text.indexOf('\\n') === -1) {
                var key = text + '|' + Math.round(r.y);
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: tag, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        classes: cls.substring(0, 45),
                    });
                }
            }
        }
        items.sort(function(a,b) { return a.y - b.y; });
        return items;
    }""")
    print(f"\n  Img2Img elements ({len(i2i_full) if i2i_full else 0}):", flush=True)
    if i2i_full:
        for item in i2i_full[:50]:
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> "
                  f"c='{item['classes'][:30]}' '{item['text']}'", flush=True)

    # B3: Check for model/style selectors specifically
    print("\n  B3: Model and style selectors...", flush=True)
    selectors = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var results = {models: [], styles: [], uploads: [], sliders: []};

        for (var el of panel.querySelectorAll('*')) {
            var cls = (el.className || '').toString();
            var r = el.getBoundingClientRect();

            // Model selector
            if ((cls.includes('model') || cls.includes('option-label') || cls.includes('select'))
                && r.width > 0 && r.height > 0) {
                results.models.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 40),
                    classes: cls.substring(0, 45),
                });
            }

            // Style selector
            if (cls.includes('style') && r.width > 0) {
                results.styles.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 40),
                    classes: cls.substring(0, 45),
                });
            }

            // Upload / source image
            if ((cls.includes('upload') || cls.includes('source') || cls.includes('pick'))
                && r.width > 0 && r.height > 0) {
                results.uploads.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 40),
                    classes: cls.substring(0, 45),
                });
            }

            // Sliders
            if ((cls.includes('slider') || cls.includes('strength') || cls.includes('range'))
                && r.width > 0) {
                results.sliders.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 40),
                    classes: cls.substring(0, 45),
                });
            }
        }
        return results;
    }""")
    if selectors:
        print(f"\n  Models ({len(selectors.get('models', []))}):", flush=True)
        for m in selectors.get('models', [])[:10]:
            print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> '{m['text']}' c='{m['classes'][:30]}'", flush=True)
        print(f"\n  Styles ({len(selectors.get('styles', []))}):", flush=True)
        for s in selectors.get('styles', [])[:10]:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> '{s['text']}' c='{s['classes'][:30]}'", flush=True)
        print(f"\n  Uploads ({len(selectors.get('uploads', []))}):", flush=True)
        for u in selectors.get('uploads', [])[:10]:
            print(f"    ({u['x']},{u['y']}) {u['w']}x{u['h']} <{u['tag']}> '{u['text']}' c='{u['classes'][:30]}'", flush=True)
        print(f"\n  Sliders ({len(selectors.get('sliders', []))}):", flush=True)
        for sl in selectors.get('sliders', [])[:10]:
            print(f"    ({sl['x']},{sl['y']}) {sl['w']}x{sl['h']} <{sl['tag']}> '{sl['text']}' c='{sl['classes'][:30]}'", flush=True)

    # B4: Check what's on the canvas (source image upload area for Img2Img)
    print("\n  B4: Canvas center elements...", flush=True)
    canvas_center = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            // Elements in the center canvas area
            if (r.x > 350 && r.x < 1100 && r.y > 100 && r.y < 800
                && r.width > 50 && r.height > 20
                && text.length > 0 && text.length < 80
                && text.indexOf('\\n') === -1
                && r.height < 100) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 60),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        // Dedupe
        var seen = new Set();
        var unique = [];
        for (var item of items) {
            var key = item.text + '|' + Math.round(item.y / 10);
            if (!seen.has(key)) {
                seen.add(key);
                unique.push(item);
            }
        }
        unique.sort(function(a,b) { return a.y - b.y; });
        return unique.slice(0, 15);
    }""")
    print(f"\n  Canvas center elements ({len(canvas_center)}):", flush=True)
    for c in canvas_center:
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> '{c['text'][:45]}' c='{c['classes'][:25]}'", flush=True)

    ss(page, "P93_05_img2img_final")

    print(f"\n\n===== PHASE 93 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
