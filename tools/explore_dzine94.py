"""Phase 94: Lip Sync AUDIO STEP + Img2Img proper open.
Flow: Results → Lip Sync → Pick Face → Next (crop) → Next (audio) → map audio upload
Then: Close dialog, open Img2Img properly
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


def click_next_in_dialog(page):
    """Click Next button in high-z dialog."""
    return page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            if (z > 900) {
                for (var btn of el.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === 'Next') {
                        btn.click();
                        return 'clicked Next in z=' + z;
                    }
                }
            }
        }
        // Try any visible Next button
        for (var btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Next' && r.width > 0 && r.height > 0 && r.y > 600) {
                btn.click();
                return 'clicked Next at y=' + Math.round(r.y);
            }
        }
        return 'Next not found';
    }""")


def map_dialog(page):
    """Map all elements in the high-z dialog."""
    return page.evaluate("""() => {
        var result = {title: '', elements: [], classes: ''};
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && r.width > 300 && r.height > 200) {
                result.classes = (el.className || '').toString().substring(0, 60);

                var seen = new Set();
                for (var child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    var ctag = child.tagName;
                    if (cr.width > 0 && cr.height > 0
                        && (ctag === 'BUTTON' || ctag === 'INPUT' || ctag === 'TEXTAREA'
                            || ctag === 'LABEL' || ctag === 'IMG'
                            || (text.length > 0 && text.length < 80
                                && text.indexOf('\\n') === -1
                                && cr.height < 80))) {
                        var key = text.substring(0,25) + '|' + Math.round(cr.y) + '|' + ctag;
                        if (!seen.has(key)) {
                            seen.add(key);
                            result.elements.push({
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
                result.elements.sort(function(a,b) { return a.y - b.y; });
                break;
            }
        }
        return result;
    }""")


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
    #  STEP 1: Open Lip Sync + Results → Lip Sync action
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: LIP SYNC → FACE → CROP → AUDIO", flush=True)
    print("=" * 60, flush=True)

    # Open Lip Sync tool first
    page.mouse.click(37, 750)  # Storyboard
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)
    page.mouse.click(37, 400)  # Lip Sync
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Open Results panel and click Lip Sync "1" button on first result
    page.evaluate("() => document.querySelector('.header-item.item-results')?.click()")
    page.wait_for_timeout(1000)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-material-library-v2');
        if (!panel) return;
        var scroll = panel.querySelector('.material-v2-result-content');
        if (scroll) scroll.scrollTop = 0;
    }""")
    page.wait_for_timeout(500)

    # Click "1" button for Lip Sync action
    ls_click = page.evaluate("""() => {
        var panel = document.querySelector('.c-material-library-v2');
        if (!panel) return 'no panel';
        var rows = panel.querySelectorAll('.label');
        for (var row of rows) {
            var lt = row.querySelector('.label-text');
            if (!lt) continue;
            var text = (lt.innerText || '').trim();
            if (text !== 'Lip Sync') continue;
            var rr = row.getBoundingClientRect();
            if (rr.y < 0 || rr.y > 800) continue;
            for (var btn of row.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === '1') {
                    btn.click();
                    return 'clicked Lip Sync 1';
                }
            }
        }
        return 'not found';
    }""")
    print(f"  {ls_click}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ---- Step 1a: "Pick a Face" dialog (face detection) ----
    print("\n  Step 1a: Pick a Face (face detection)...", flush=True)
    dialog = map_dialog(page)
    print(f"  Dialog class: {dialog.get('classes', 'none')}", flush=True)
    for e in dialog.get('elements', [])[:10]:
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:40]}'", flush=True)
    ss(page, "P94_01_pick_face")

    # Click Next (skip face selection — already auto-selected)
    r1 = click_next_in_dialog(page)
    print(f"  Next 1: {r1}", flush=True)
    page.wait_for_timeout(2000)

    # ---- Step 1b: Crop dialog ----
    print("\n  Step 1b: Crop step...", flush=True)
    dialog2 = map_dialog(page)
    print(f"  Dialog class: {dialog2.get('classes', 'none')}", flush=True)
    for e in dialog2.get('elements', [])[:15]:
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:40]}'", flush=True)
    ss(page, "P94_02_crop")

    # Click Next again (skip crop — keep original)
    r2 = click_next_in_dialog(page)
    print(f"  Next 2: {r2}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ---- Step 1c: Audio step? Or direct to panel? ----
    print("\n  Step 1c: After second Next...", flush=True)
    dialog3 = map_dialog(page)
    has_dialog = len(dialog3.get('elements', [])) > 0
    print(f"  Has dialog: {has_dialog}", flush=True)
    if has_dialog:
        print(f"  Dialog class: {dialog3.get('classes', 'none')}", flush=True)
        for e in dialog3.get('elements', [])[:20]:
            extra = ""
            if e.get('type'): extra += f" type={e['type']}"
            if e.get('accept'): extra += f" accept={e['accept']}"
            print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> c='{e.get('classes','')[:25]}' '{e['text'][:40]}'{extra}", flush=True)
    ss(page, "P94_03_audio_or_panel")

    # Check the Lip Sync panel state — did the face get set?
    panel_state = page.evaluate("""() => {
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
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        tag: child.tagName,
                        classes: (child.className || '').toString().substring(0, 40),
                    });
                }
            }
        }
        items.sort(function(a,b) { return a.y - b.y; });

        // Check for images in panel (face preview)
        var imgs = [];
        for (var img of p.querySelectorAll('img')) {
            var ir = img.getBoundingClientRect();
            if (ir.width > 10) {
                imgs.push({
                    src: (img.src || '').substring(0, 100),
                    x: Math.round(ir.x), y: Math.round(ir.y),
                    w: Math.round(ir.width), h: Math.round(ir.height),
                });
            }
        }
        return {items: items, imgs: imgs};
    }""")
    print(f"\n  Lip Sync panel state:", flush=True)
    if panel_state:
        for item in panel_state.get('items', [])[:20]:
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> '{item['text']}'", flush=True)
        print(f"\n  Panel images ({len(panel_state.get('imgs', []))}):", flush=True)
        for img in panel_state.get('imgs', []):
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src']}", flush=True)

    # Check canvas area for audio upload elements
    canvas_elements = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var cls = (el.className || '').toString();
            // Canvas area elements (between left panel and right results)
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
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 60),
                        tag: el.tagName,
                        classes: cls.substring(0, 40),
                    });
                }
            }
        }
        items.sort(function(a,b) { return a.y - b.y; });
        return items.slice(0, 20);
    }""")
    print(f"\n  Canvas area elements ({len(canvas_elements)}):", flush=True)
    for c in canvas_elements:
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:25]}' '{c['text'][:45]}'", flush=True)

    # ============================================================
    #  STEP 2: If still in dialog, click through to audio
    # ============================================================
    if has_dialog:
        print("\n" + "=" * 60, flush=True)
        print("  STEP 2: CONTINUE DIALOG TO AUDIO", flush=True)
        print("=" * 60, flush=True)

        r3 = click_next_in_dialog(page)
        print(f"  Next 3: {r3}", flush=True)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        ss(page, "P94_04_step3")

        dialog4 = map_dialog(page)
        if dialog4.get('elements'):
            print(f"  Dialog elements ({len(dialog4['elements'])}):", flush=True)
            for e in dialog4['elements'][:20]:
                extra = ""
                if e.get('type'): extra += f" type={e['type']}"
                if e.get('accept'): extra += f" accept={e['accept']}"
                print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:45]}'{extra}", flush=True)

    # ============================================================
    #  STEP 3: Check for audio on canvas/panel after face set
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: AUDIO UPLOAD SEARCH", flush=True)
    print("=" * 60, flush=True)

    # Search for ALL audio/voice/upload elements that are now visible
    audio_search = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var cls = (el.className || '').toString();
            if (r.width > 0 && r.height > 0 && r.x > 0) {
                if (text.includes('audio') || text.includes('Audio')
                    || text.includes('Upload') || text.includes('upload')
                    || text.includes('voice') || text.includes('Voice')
                    || text.includes('Record') || text.includes('.mp3')
                    || text.includes('.wav') || text.includes('Browse')
                    || cls.includes('audio') || cls.includes('upload-audio')
                    || cls.includes('voice')) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 60),
                        tag: el.tagName,
                        classes: cls.substring(0, 40),
                    });
                }
            }
        }
        return items.slice(0, 20);
    }""")
    print(f"\n  Audio elements ({len(audio_search)}):", flush=True)
    for a in audio_search:
        print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> c='{a['classes'][:25]}' '{a['text'][:45]}'", flush=True)

    # Check ALL file inputs (including hidden ones)
    file_inputs = page.evaluate("""() => {
        var inputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            var r = inp.getBoundingClientRect();
            inputs.push({
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                accept: inp.accept || 'any',
                id: inp.id || '',
                name: inp.name || '',
                visible: r.width > 0 && r.height > 0,
                parent: (inp.parentElement?.className || '').toString().substring(0, 40),
            });
        }
        return inputs;
    }""")
    print(f"\n  ALL file inputs ({len(file_inputs)}):", flush=True)
    for f in file_inputs:
        vis = " VISIBLE" if f['visible'] else ""
        print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']}{vis} accept='{f['accept']}' id='{f['id']}' parent='{f['parent'][:30]}'", flush=True)

    ss(page, "P94_05_final_state")

    # ============================================================
    #  STEP 4: IMG2IMG — Close everything and open fresh
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 4: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    # Close everything
    for _ in range(5):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.evaluate("""() => {
        var c1 = document.querySelector('.c-gen-config.show .ico-close');
        if (c1) c1.click();
    }""")
    page.wait_for_timeout(1000)

    # Verify panel is closed
    panel_gone = page.evaluate("() => !document.querySelector('.c-gen-config.show')")
    print(f"  Panel closed: {panel_gone}", flush=True)

    # Click a distant tool first
    page.mouse.click(37, 750)  # Storyboard or Instant Storyboard
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Close that panel
    page.evaluate("""() => {
        var c = document.querySelector('.c-gen-config.show .ico-close') ||
                document.querySelector('.panels.show .ico-close');
        if (c) c.click();
    }""")
    page.wait_for_timeout(1000)

    # Now click Img2Img
    print("  Clicking Img2Img...", flush=True)
    page.mouse.click(37, 240)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Check panel
    panel_info = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        return {
            classes: (p.className || '').toString(),
            header: '',
        };
    }""")
    print(f"  Panel: {panel_info}", flush=True)

    if panel_info and 'img2img' not in panel_info.get('classes', ''):
        # Try finding the correct toolbar position by reading tool labels
        print("  Not Img2Img — scanning toolbar...", flush=True)
        toolbar = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.tool-group')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 30),
                });
            }
            return items;
        }""")
        print(f"\n  Toolbar items ({len(toolbar)}):", flush=True)
        for t in toolbar:
            print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}'", flush=True)

        # Find Img2Img and click it
        i2i_clicked = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.tool-group')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Img2Img')) {
                    el.click();
                    var r = el.getBoundingClientRect();
                    return 'clicked at (' + Math.round(r.x) + ',' + Math.round(r.y) + ')';
                }
            }
            return 'not found';
        }""")
        print(f"  Img2Img click: {i2i_clicked}", flush=True)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        dismiss_popups(page)

    # Full panel mapping
    i2i_map = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;

        var items = [];
        var seen = new Set();

        for (var child of panel.querySelectorAll('*')) {
            var r = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            var cls = (child.className || '').toString();
            var tag = child.tagName;

            if (r.width > 0 && r.height > 0 && r.height < 100) {
                // Include all meaningful elements
                if (tag === 'BUTTON' || tag === 'INPUT' || tag === 'IMG'
                    || cls.includes('slider') || cls.includes('range')
                    || (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1)) {
                    var key = (text || cls).substring(0,25) + '|' + Math.round(r.y);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: tag, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 50),
                            classes: cls.substring(0, 45),
                            src: tag === 'IMG' ? (child.src || '').substring(0, 80) : '',
                        });
                    }
                }
            }
        }
        items.sort(function(a,b) { return a.y - b.y; });
        return {
            panelClass: (panel.className || '').toString(),
            items: items,
        };
    }""")

    if i2i_map:
        print(f"\n  Panel class: {i2i_map.get('panelClass', '')}", flush=True)
        print(f"  Elements ({len(i2i_map.get('items', []))}):", flush=True)
        for item in i2i_map.get('items', [])[:50]:
            src = f" src={item['src'][:40]}" if item.get('src') else ''
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> "
                  f"c='{item['classes'][:30]}' '{item['text'][:35]}'{src}", flush=True)

    ss(page, "P94_06_img2img")

    print(f"\n\n===== PHASE 94 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
