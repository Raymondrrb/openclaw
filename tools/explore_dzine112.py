"""Phase 112: Deep Character + Enhance & Upscale + Upload mechanism.
P111 confirmed sidebar positions:
  Upload=81, Assets=136, Txt2Img=197, Img2Img=252, Character=306,
  AI Video=361, Lip Sync=425, Video Editor=490, Motion Control=551,
  Enhance&Upscale=628, Image Editor=698, Storyboard=766

Character panel has: Build Character, Manage, Generate Images, Insert Character,
Character Sheet, Generate 360° Video.

Goal: 1) Character > Build Your Character flow
      2) Character > Generate Images flow
      3) Character > Insert Character flow
      4) Enhance & Upscale panel (at y=628)
      5) Upload mechanism — how to upload external images to canvas
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


def close_all_panels(page):
    """Close all panels and dialogs."""
    page.evaluate("""() => {
        // Close gen config panels
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) {
            el.click();
        }
        // Close .panels.show
        for (var el of document.querySelectorAll('.panels.show .ico-close')) {
            el.click();
        }
        // Close lip sync panel
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
        // Close popup mounts
        for (var el of document.querySelectorAll('.popup-mount-node .ico-close')) {
            el.click();
        }
    }""")
    page.wait_for_timeout(1000)


def open_sidebar_tool(page, target_y):
    """Open sidebar tool by panel toggle."""
    close_all_panels(page)
    page.wait_for_timeout(500)
    # Click distant tool first (Storyboard)
    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    close_all_panels(page)
    page.wait_for_timeout(500)
    # Click target
    page.mouse.click(40, target_y)
    page.wait_for_timeout(2500)
    close_dialogs(page)


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
    #  STEP 1: Open Character panel properly (y=306)
    # ============================================================
    print("\n=== STEP 1: Open Character panel ===", flush=True)

    open_sidebar_tool(page, 306)

    # Verify it's the Character panel
    panel_check = page.evaluate("""() => {
        var panel = document.querySelector('.panels.show');
        if (!panel) return {error: 'no .panels.show'};
        var text = (panel.innerText || '').substring(0, 300);
        return {
            class: (panel.className || '').toString().substring(0, 60),
            title: text.substring(0, 50),
            isCharacter: text.includes('Character') && text.includes('Build'),
        };
    }""")
    print(f"  Panel: {json.dumps(panel_check)}", flush=True)

    if not panel_check.get('isCharacter'):
        print("  Not Character panel, trying direct click...", flush=True)
        close_all_panels(page)
        page.wait_for_timeout(500)
        page.mouse.click(40, 306)
        page.wait_for_timeout(3000)
        close_dialogs(page)

    ss(page, "P112_01_character_panel")

    # ============================================================
    #  STEP 2: Click "Build Your Character"
    # ============================================================
    print("\n=== STEP 2: Build Your Character ===", flush=True)

    build_btn = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button, [class*="btn"]')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text.includes('Build Your Character') && r.width > 100) {
                return {
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    text: text,
                };
            }
        }
        return null;
    }""")
    print(f"  Build btn: {json.dumps(build_btn)}", flush=True)

    if build_btn:
        page.mouse.click(build_btn['x'], build_btn['y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        # Map the Build Character dialog/flow
        build_ui = page.evaluate("""() => {
            // Check for dialog/popup
            var dialogs = [];
            for (var el of document.querySelectorAll('[class*="dialog"], [class*="modal"], [class*="popup"], [class*="overlay"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 200 && r.height > 200) {
                    dialogs.push({
                        class: (el.className || '').toString().substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').substring(0, 400),
                    });
                }
            }

            // Check for new panel content
            var panel = document.querySelector('.panels.show');
            var panelText = panel ? (panel.innerText || '').substring(0, 500) : '';

            // Check for any new full-page content
            var body = document.body.innerText || '';
            var hasCharacterBuilder = body.includes('character name') || body.includes('Character Name')
                || body.includes('Upload') || body.includes('reference image');

            return {
                dialogs: dialogs.slice(0, 3),
                panelText: panelText,
                hasCharacterBuilder: hasCharacterBuilder,
            };
        }""")

        print(f"  Dialogs: {len(build_ui.get('dialogs', []))}", flush=True)
        for d in build_ui.get('dialogs', []):
            print(f"    .{d['class'][:60]}", flush=True)
            print(f"      ({d['x']},{d['y']}) {d['w']}x{d['h']}", flush=True)
            print(f"      text: {d['text'][:200]}", flush=True)
        print(f"  Panel text: {build_ui.get('panelText', '')[:200]}", flush=True)
        print(f"  Has character builder: {build_ui.get('hasCharacterBuilder')}", flush=True)

    ss(page, "P112_02_build_character")

    # ============================================================
    #  STEP 3: Map the Build Character form/flow
    # ============================================================
    print("\n=== STEP 3: Build Character form ===", flush=True)

    build_form = page.evaluate("""() => {
        // Look for character building UI elements anywhere in the page
        var elements = [];
        for (var el of document.querySelectorAll('input, textarea, [contenteditable="true"], button, [class*="upload"], [class*="pick"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 30 || r.height < 15 || r.x < 60) continue;
            // Only elements in the left panel area (x < 400) or dialog area
            if (r.x > 400 && r.x < 800) continue;  // Skip canvas area
            var text = (el.innerText || '').trim();
            var placeholder = el.getAttribute('placeholder') || '';
            if (text.length > 0 || placeholder.length > 0 || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                elements.push({
                    tag: el.tagName,
                    type: el.type || '',
                    class: (el.className || '').toString().substring(0, 60),
                    text: text.substring(0, 50),
                    placeholder: placeholder.substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        // Check if we navigated to a different page
        var url = window.location.href;

        return {elements: elements.slice(0, 20), url: url};
    }""")

    print(f"  URL: {build_form.get('url')}", flush=True)
    print(f"  Form elements ({len(build_form.get('elements', []))}):", flush=True)
    for e in build_form.get('elements', []):
        print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:30]}' ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)
        if e.get('placeholder'):
            print(f"      placeholder: '{e['placeholder']}'", flush=True)

    ss(page, "P112_03_build_form")

    # ============================================================
    #  STEP 4: Go back and explore "Generate Images" option
    # ============================================================
    print("\n=== STEP 4: Generate Images with character ===", flush=True)

    # Navigate back if needed
    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    wait_for_canvas(page)
    close_dialogs(page)

    open_sidebar_tool(page, 306)

    # Click "Generate Images" option
    gen_images = page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="collapse-option"], button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Generate Images') && r.width > 100 && r.x < 350) {
                return {
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    text: text.substring(0, 60),
                };
            }
        }
        return null;
    }""")
    print(f"  Generate Images btn: {json.dumps(gen_images)}", flush=True)

    if gen_images:
        page.mouse.click(gen_images['x'], gen_images['y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        # Map the expanded content
        gen_content = page.evaluate("""() => {
            var panel = document.querySelector('.panels.show');
            if (!panel) return {error: 'no panel'};

            var text = (panel.innerText || '').substring(0, 600);

            // Find all interactive elements in the panel
            var elements = [];
            for (var el of panel.querySelectorAll('input, textarea, button, [class*="upload"], [class*="pick"], [class*="select"], [class*="dropdown"]')) {
                var r = el.getBoundingClientRect();
                if (r.width < 20 || r.height < 10) continue;
                elements.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 40),
                    placeholder: el.getAttribute('placeholder') || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }

            // Check for character selector
            var charSelect = null;
            for (var el of panel.querySelectorAll('[class*="character"], [class*="avatar"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 40 && r.height > 40) {
                    charSelect = {
                        class: (el.className || '').toString().substring(0, 60),
                        text: (el.innerText || '').trim().substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                    break;
                }
            }

            return {
                fullText: text,
                elements: elements.slice(0, 15),
                charSelect: charSelect,
            };
        }""")

        print(f"  Full text:\n{gen_content.get('fullText', '')[:400]}", flush=True)
        print(f"\n  Elements ({len(gen_content.get('elements', []))}):", flush=True)
        for e in gen_content.get('elements', []):
            print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:30]}' ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)
        print(f"  Character selector: {json.dumps(gen_content.get('charSelect'))}", flush=True)

    ss(page, "P112_04_generate_images")

    # ============================================================
    #  STEP 5: Go back and explore "Insert Character"
    # ============================================================
    print("\n=== STEP 5: Insert Character ===", flush=True)

    # Back to character panel
    open_sidebar_tool(page, 306)

    insert_char = page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="collapse-option"], button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Insert Character') && r.width > 100 && r.x < 350) {
                return {
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    text: text.substring(0, 60),
                };
            }
        }
        return null;
    }""")
    print(f"  Insert Character btn: {json.dumps(insert_char)}", flush=True)

    if insert_char:
        page.mouse.click(insert_char['x'], insert_char['y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        insert_content = page.evaluate("""() => {
            var panel = document.querySelector('.panels.show, .c-gen-config.show');
            if (!panel) return {error: 'no panel'};
            var text = (panel.innerText || '').substring(0, 500);

            var elements = [];
            for (var el of panel.querySelectorAll('input, textarea, button, [class*="upload"], [class*="pick"]')) {
                var r = el.getBoundingClientRect();
                if (r.width < 20 || r.height < 10) continue;
                elements.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }

            return {fullText: text, elements: elements.slice(0, 15)};
        }""")

        print(f"  Full text:\n{insert_content.get('fullText', '')[:300]}", flush=True)
        print(f"  Elements ({len(insert_content.get('elements', []))}):", flush=True)
        for e in insert_content.get('elements', []):
            print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:30]}' ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P112_05_insert_character")

    # ============================================================
    #  STEP 6: Open Enhance & Upscale (y=628)
    # ============================================================
    print("\n=== STEP 6: Enhance & Upscale ===", flush=True)

    open_sidebar_tool(page, 628)

    eu_panel = page.evaluate("""() => {
        var panel = document.querySelector('.panels.show, .c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').substring(0, 600);
        var title = panel.querySelector('h5');

        var elements = [];
        for (var el of panel.querySelectorAll('input, textarea, button, [class*="upload"], [class*="pick"], [class*="slider"], [class*="option"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 20 || r.height < 10) continue;
            elements.push({
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 40),
                placeholder: el.getAttribute('placeholder') || '',
                disabled: el.disabled,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        return {
            panelClass: (panel.className || '').toString().substring(0, 80),
            title: title ? (title.innerText || '').trim() : 'none',
            fullText: text,
            elements: elements.slice(0, 20),
        };
    }""")

    print(f"  Panel: .{eu_panel.get('panelClass', '')[:60]}", flush=True)
    print(f"  Title: {eu_panel.get('title')}", flush=True)
    print(f"\n  Full text:\n{eu_panel.get('fullText', '')[:400]}", flush=True)
    print(f"\n  Elements ({len(eu_panel.get('elements', []))}):", flush=True)
    for e in eu_panel.get('elements', []):
        print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:30]}' ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P112_06_enhance_upscale")

    # ============================================================
    #  STEP 7: Explore Upload mechanism
    # ============================================================
    print("\n=== STEP 7: Upload mechanism ===", flush=True)

    # Click Upload in sidebar (y=81)
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check what opened
    upload_state = page.evaluate("""() => {
        // Check for file inputs
        var fileInputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            var r = inp.getBoundingClientRect();
            fileInputs.push({
                accept: inp.accept || '',
                multiple: inp.multiple,
                id: inp.id || '',
                class: (inp.className || '').toString().substring(0, 40),
                visible: r.width > 0 && r.height > 0,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Check panels
        var panels = [];
        for (var el of document.querySelectorAll('.panels.show, .c-gen-config.show, [class*="upload"][class*="panel"]')) {
            var r = el.getBoundingClientRect();
            panels.push({
                class: (el.className || '').toString().substring(0, 80),
                text: (el.innerText || '').substring(0, 200),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Check for drag/drop areas
        var dropAreas = [];
        for (var el of document.querySelectorAll('[class*="drop"], [class*="drag"], [class*="upload-area"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 50 && r.height > 50) {
                dropAreas.push({
                    class: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        return {fileInputs: fileInputs, panels: panels, dropAreas: dropAreas};
    }""")

    print(f"  File inputs: {len(upload_state.get('fileInputs', []))}", flush=True)
    for fi in upload_state.get('fileInputs', []):
        print(f"    accept='{fi['accept']}' multiple={fi['multiple']} visible={fi['visible']} ({fi['x']},{fi['y']}) {fi['w']}x{fi['h']}", flush=True)

    print(f"  Panels: {len(upload_state.get('panels', []))}", flush=True)
    for p in upload_state.get('panels', []):
        print(f"    .{p['class'][:60]}", flush=True)
        print(f"      ({p['x']},{p['y']}) {p['w']}x{p['h']}", flush=True)
        print(f"      text: {p['text'][:100]}", flush=True)

    print(f"  Drop areas: {len(upload_state.get('dropAreas', []))}", flush=True)
    for d in upload_state.get('dropAreas', []):
        print(f"    .{d['class'][:50]} '{d['text'][:40]}' ({d['x']},{d['y']}) {d['w']}x{d['h']}", flush=True)

    # Try clicking the Upload icon area more precisely
    page.mouse.click(30, 76)
    page.wait_for_timeout(2000)

    # Check again
    upload_state2 = page.evaluate("""() => {
        var fileInputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            fileInputs.push({
                accept: inp.accept || '',
                id: inp.id || '',
                name: inp.name || '',
                class: (inp.className || '').toString().substring(0, 40),
            });
        }

        // Check if Assets panel opened with upload option
        var uploadBtn = null;
        for (var el of document.querySelectorAll('[class*="upload"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.width > 20 && r.height > 20 && text.length > 0 && r.x < 400) {
                uploadBtn = {
                    class: (el.className || '').toString().substring(0, 60),
                    text: text.substring(0, 40),
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
            }
        }

        return {fileInputs: fileInputs, uploadBtn: uploadBtn};
    }""")

    print(f"\n  File inputs (2nd check): {len(upload_state2.get('fileInputs', []))}", flush=True)
    for fi in upload_state2.get('fileInputs', []):
        print(f"    accept='{fi['accept']}' #{fi['id']} .{fi['class']}", flush=True)
    print(f"  Upload button: {json.dumps(upload_state2.get('uploadBtn'))}", flush=True)

    ss(page, "P112_07_upload")

    # ============================================================
    #  STEP 8: Check hidden file inputs and upload buttons
    # ============================================================
    print("\n=== STEP 8: All upload-related elements ===", flush=True)

    all_uploads = page.evaluate("""() => {
        var items = [];

        // All file inputs (including hidden)
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            items.push({
                type: 'file-input',
                accept: inp.accept || '',
                id: inp.id || '',
                name: inp.name || '',
                class: (inp.className || '').toString().substring(0, 40),
                parentClass: inp.parentElement ? (inp.parentElement.className || '').toString().substring(0, 40) : '',
            });
        }

        // All elements with "upload" in class
        for (var el of document.querySelectorAll('[class*="upload"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 5) continue;
            items.push({
                type: 'upload-element',
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // All elements with "import" in class
        for (var el of document.querySelectorAll('[class*="import"]')) {
            var r = el.getBoundingClientRect();
            items.push({
                type: 'import-element',
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        return items;
    }""")

    print(f"  Upload-related elements ({len(all_uploads)}):", flush=True)
    for item in all_uploads[:15]:
        if item['type'] == 'file-input':
            print(f"    [FILE INPUT] accept='{item['accept']}' #{item['id']} parent=.{item['parentClass']}", flush=True)
        else:
            print(f"    [{item['type'].upper()}] <{item['tag']}> .{item['class'][:40]} '{item['text'][:25]}' ({item['x']},{item['y']}) {item['w']}x{item['h']}", flush=True)

    # ============================================================
    #  STEP 9: Try the Assets panel upload button
    # ============================================================
    print("\n=== STEP 9: Assets upload button ===", flush=True)

    # Open Assets panel (y=136)
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 136)
    page.wait_for_timeout(2000)

    # Find and describe the upload button in Assets
    assets_upload = page.evaluate("""() => {
        var panel = document.querySelector('.panels.show');
        if (!panel) return {error: 'no panel'};

        // Find upload-image button
        var uploadBtn = panel.querySelector('.upload-image, [class*="upload"]');
        if (uploadBtn) {
            var r = uploadBtn.getBoundingClientRect();
            return {
                class: (uploadBtn.className || '').toString().substring(0, 60),
                text: (uploadBtn.innerText || '').trim().substring(0, 40),
                tag: uploadBtn.tagName,
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
                title: uploadBtn.title || '',
            };
        }
        return null;
    }""")
    print(f"  Assets upload btn: {json.dumps(assets_upload)}", flush=True)

    if assets_upload and not assets_upload.get('error'):
        # Click the upload button and check for file chooser
        print("  Clicking upload button to check mechanism...", flush=True)

        # Check if clicking triggers a file_chooser event
        has_file_input = page.evaluate("""(x, y) => {
            // Check if there's a hidden file input that gets triggered
            var el = document.elementFromPoint(x, y);
            if (!el) return null;
            return {
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                type: el.type || '',
                // Check for nearby file input
                sibling: null,
            };
        }""", assets_upload['x'], assets_upload['y'])
        print(f"  Element at upload coords: {json.dumps(has_file_input)}", flush=True)

    ss(page, "P112_08_assets_upload")

    print(f"\n\n===== PHASE 112 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
