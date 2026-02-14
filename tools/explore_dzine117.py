"""Phase 117: Image Editor + Expression Edit + Face Swap + Upload via drag-and-drop.
P116 SUCCESS: Ray character selected and image generated (4 credits, 39s).
Key: JS-click hidden button.item.s-2 in .c-character-list

Remaining unexplored tools:
- Image Editor (sidebar y=698)
- Expression Edit (result action)
- Face Swap (result action)
- Upload mechanism (try drag-and-drop, clipboard paste)

Goal: 1) Map Image Editor panel
      2) Map Expression Edit (from result action button)
      3) Map Face Swap (from result action button)
      4) Test drag-and-drop upload to canvas
      5) Test clipboard paste to canvas
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
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
    }""")
    page.wait_for_timeout(1000)


def open_sidebar_tool(page, target_y):
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    close_all_panels(page)
    page.wait_for_timeout(500)
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
    #  STEP 1: Image Editor panel (y=698)
    # ============================================================
    print("\n=== STEP 1: Image Editor ===", flush=True)

    open_sidebar_tool(page, 698)

    ie_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show, .panels.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').substring(0, 600);
        var title = panel.querySelector('h5');

        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [class*="upload"], [class*="option"], [class*="slider"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 20 || r.height < 10) continue;
            elements.push({
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 50),
                text: (el.innerText || '').trim().substring(0, 30),
                disabled: el.disabled,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        return {
            panelClass: (panel.className || '').toString().substring(0, 80),
            title: title ? (title.innerText || '').trim() : '',
            fullText: text,
            elements: elements.slice(0, 20),
        };
    }""")

    print(f"  Panel: .{ie_panel.get('panelClass', '')[:60]}", flush=True)
    print(f"  Title: {ie_panel.get('title')}", flush=True)
    print(f"\n  Full text:\n{ie_panel.get('fullText', '')[:400]}", flush=True)
    print(f"\n  Elements ({len(ie_panel.get('elements', []))}):", flush=True)
    for e in ie_panel.get('elements', []):
        print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:25]}' ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P117_01_image_editor")

    # ============================================================
    #  STEP 2: Check result action buttons (Expression Edit, Face Swap)
    # ============================================================
    print("\n=== STEP 2: Result action buttons ===", flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, [class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Results') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Map all unique result action button types
    result_actions = page.evaluate("""() => {
        var actions = new Map();
        for (var el of document.querySelectorAll('.result-item')) {
            var btns = el.querySelectorAll('button, [class*="action"], [class*="btn"]');
            for (var btn of btns) {
                var text = (btn.innerText || '').trim();
                var cls = (btn.className || '').toString();
                if (text.length > 0 && text.length < 30 && !actions.has(text)) {
                    var r = btn.getBoundingClientRect();
                    actions.set(text, {
                        text: text,
                        class: cls.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
        }
        return Array.from(actions.values());
    }""")

    print(f"  Unique action buttons ({len(result_actions)}):", flush=True)
    for a in result_actions:
        print(f"    '{a['text']}' .{a['class'][:40]} ({a['x']},{a['y']}) {a['w']}x{a['h']}", flush=True)

    # ============================================================
    #  STEP 3: Click "Expression Edit" on first result
    # ============================================================
    print("\n=== STEP 3: Expression Edit ===", flush=True)

    expr_btn = page.evaluate("""() => {
        for (var el of document.querySelectorAll('.result-item button, .result-item [class*="btn"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Expression Edit' && r.width > 50) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    print(f"  Expression Edit btn: {json.dumps(expr_btn)}", flush=True)

    if expr_btn:
        page.mouse.click(expr_btn['x'], expr_btn['y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        expr_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show, .panels.show');
            if (!panel) return {error: 'no panel'};
            var text = (panel.innerText || '').substring(0, 500);
            var title = panel.querySelector('h5');

            var elements = [];
            for (var el of panel.querySelectorAll('button, textarea, input, [class*="option"]')) {
                var r = el.getBoundingClientRect();
                if (r.width < 20 || r.height < 10) continue;
                elements.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 50),
                    text: (el.innerText || '').trim().substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }

            return {
                title: title ? (title.innerText || '').trim() : '',
                fullText: text,
                elements: elements.slice(0, 15),
            };
        }""")

        print(f"  Title: {expr_panel.get('title')}", flush=True)
        print(f"  Full text:\n{expr_panel.get('fullText', '')[:300]}", flush=True)
        print(f"\n  Elements ({len(expr_panel.get('elements', []))}):", flush=True)
        for e in expr_panel.get('elements', []):
            print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:25]}' ({e['x']},{e['y']}) w={e['w']}", flush=True)

        ss(page, "P117_02_expression_edit")
    else:
        # Scroll results to find it
        print("  Expression Edit not visible, scrolling...", flush=True)
        page.evaluate("""() => {
            var panel = document.querySelector('.c-material-library-v2');
            if (panel) panel.scrollTop = 0;
        }""")
        page.wait_for_timeout(500)

    # ============================================================
    #  STEP 4: Click "Face Swap" on first result
    # ============================================================
    print("\n=== STEP 4: Face Swap ===", flush=True)

    # Go back first
    close_all_panels(page)
    page.wait_for_timeout(500)

    face_swap_btn = page.evaluate("""() => {
        for (var el of document.querySelectorAll('.result-item button, .result-item [class*="btn"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Face Swap' && r.width > 50) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    print(f"  Face Swap btn: {json.dumps(face_swap_btn)}", flush=True)

    if face_swap_btn:
        page.mouse.click(face_swap_btn['x'], face_swap_btn['y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        fs_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show, .panels.show');
            if (!panel) return {error: 'no panel'};
            var text = (panel.innerText || '').substring(0, 500);

            var elements = [];
            for (var el of panel.querySelectorAll('button, textarea, input, [class*="option"], [class*="upload"]')) {
                var r = el.getBoundingClientRect();
                if (r.width < 20 || r.height < 10) continue;
                elements.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 50),
                    text: (el.innerText || '').trim().substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }

            return {fullText: text, elements: elements.slice(0, 15)};
        }""")

        print(f"  Full text:\n{fs_panel.get('fullText', '')[:300]}", flush=True)
        print(f"\n  Elements ({len(fs_panel.get('elements', []))}):", flush=True)
        for e in fs_panel.get('elements', []):
            print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:25]}' ({e['x']},{e['y']}) w={e['w']}", flush=True)

        ss(page, "P117_03_face_swap")

    # ============================================================
    #  STEP 5: Test canvas drag-and-drop upload
    # ============================================================
    print("\n=== STEP 5: Drag-and-drop upload test ===", flush=True)

    # Create a small test PNG image in memory and try to drop it on canvas
    # First, check what element receives drag events
    drop_targets = page.evaluate("""() => {
        // Find elements with drag event handlers
        var targets = [];

        // Check the main canvas container
        var mainCanvas = document.querySelector('.canvas-container, .fabric-container, #canvas-wrapper');
        if (mainCanvas) {
            var r = mainCanvas.getBoundingClientRect();
            targets.push({
                class: (mainCanvas.className || '').toString().substring(0, 50),
                tag: mainCanvas.tagName,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Check the workspace/editor area
        var workspace = document.querySelector('.workspace, .editor-area, .canvas-editor, [class*="workspace"]');
        if (workspace) {
            var r = workspace.getBoundingClientRect();
            targets.push({
                class: (workspace.className || '').toString().substring(0, 50),
                tag: workspace.tagName,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Check the actual canvas area between sidebar and results
        for (var el of document.querySelectorAll('[class*="canvas"][class*="container"], [class*="editor"][class*="container"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 500 && r.height > 400 && r.x > 50 && r.x < 500) {
                targets.push({
                    class: (el.className || '').toString().substring(0, 50),
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        return targets;
    }""")

    print(f"  Potential drop targets ({len(drop_targets)}):", flush=True)
    for t in drop_targets:
        print(f"    <{t['tag']}> .{t['class'][:40]} ({t['x']},{t['y']}) {t['w']}x{t['h']}", flush=True)

    # Try simulating a drop event on the canvas area
    print("\n  Simulating drag-and-drop with DataTransfer...", flush=True)
    drop_result = page.evaluate("""() => {
        // Find the canvas area
        var target = document.querySelector('.canvas-container') ||
                     document.querySelector('#canvas') ||
                     document.querySelector('.lower-canvas');
        if (!target) {
            // Try the large area between sidebar and results
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 200 && r.width > 800 && r.height > 600) {
                    target = el;
                    break;
                }
            }
        }
        if (!target) return {error: 'no target'};

        // Create a small test image blob
        var canvas = document.createElement('canvas');
        canvas.width = 100;
        canvas.height = 100;
        var ctx2d = canvas.getContext('2d');
        ctx2d.fillStyle = 'red';
        ctx2d.fillRect(0, 0, 100, 100);

        // Try to create a File from the canvas
        try {
            var dataUrl = canvas.toDataURL('image/png');
            var blob = (function(dataUrl) {
                var arr = dataUrl.split(',');
                var mime = arr[0].match(/:(.*?);/)[1];
                var bstr = atob(arr[1]);
                var n = bstr.length;
                var u8arr = new Uint8Array(n);
                while(n--) { u8arr[n] = bstr.charCodeAt(n); }
                return new Blob([u8arr], {type: mime});
            })(dataUrl);

            var file = new File([blob], 'test.png', {type: 'image/png'});
            var dt = new DataTransfer();
            dt.items.add(file);

            // Dispatch events
            var r = target.getBoundingClientRect();
            var opts = {
                bubbles: true,
                cancelable: true,
                dataTransfer: dt,
                clientX: Math.round(r.x + r.width/2),
                clientY: Math.round(r.y + r.height/2),
            };

            target.dispatchEvent(new DragEvent('dragenter', opts));
            target.dispatchEvent(new DragEvent('dragover', opts));
            target.dispatchEvent(new DragEvent('drop', opts));

            return {
                success: true,
                target: (target.className || '').toString().substring(0, 40),
                tag: target.tagName,
            };
        } catch(e) {
            return {error: e.message};
        }
    }""")
    print(f"  Drop result: {json.dumps(drop_result)}", flush=True)
    page.wait_for_timeout(3000)

    # Check if anything changed
    drop_check = page.evaluate("""() => {
        // Check for new layers
        var layers = document.querySelectorAll('.layer-item');
        // Check for new uploads in assets
        var uploads = document.querySelector('.file-item.upload');
        // Check for new toast message
        var toast = document.querySelector('.show-message');
        var toastText = toast ? (toast.innerText || '').trim() : '';

        return {
            layerCount: layers.length,
            hasUpload: !!uploads,
            toast: toastText.substring(0, 60),
        };
    }""")
    print(f"  After drop: {json.dumps(drop_check)}", flush=True)

    ss(page, "P117_04_drop_test")

    # ============================================================
    #  STEP 6: Test clipboard paste (Cmd+V)
    # ============================================================
    print("\n=== STEP 6: Clipboard paste test ===", flush=True)

    # Put an image on the clipboard using the canvas API
    paste_result = page.evaluate("""() => {
        // Create a small test image
        var canvas = document.createElement('canvas');
        canvas.width = 200;
        canvas.height = 200;
        var ctx2d = canvas.getContext('2d');
        ctx2d.fillStyle = 'blue';
        ctx2d.fillRect(0, 0, 200, 200);
        ctx2d.fillStyle = 'white';
        ctx2d.font = '20px Arial';
        ctx2d.fillText('Test Upload', 30, 110);

        // Try clipboard.write
        try {
            canvas.toBlob(function(blob) {
                if (blob) {
                    var item = new ClipboardItem({'image/png': blob});
                    navigator.clipboard.write([item]).then(function() {
                        window._clipboardReady = true;
                    }).catch(function(e) {
                        window._clipboardError = e.message;
                    });
                }
            });
            return {attempted: true};
        } catch(e) {
            return {error: e.message};
        }
    }""")
    print(f"  Clipboard write: {json.dumps(paste_result)}", flush=True)
    page.wait_for_timeout(2000)

    clipboard_check = page.evaluate("() => ({ready: window._clipboardReady, error: window._clipboardError})")
    print(f"  Clipboard status: {json.dumps(clipboard_check)}", flush=True)

    if clipboard_check.get('ready'):
        # Focus canvas and paste
        page.mouse.click(700, 450)  # Click canvas center
        page.wait_for_timeout(500)
        page.keyboard.press("Meta+v")
        page.wait_for_timeout(3000)

        paste_check = page.evaluate("""() => {
            var layers = document.querySelectorAll('.layer-item');
            var toast = document.querySelector('.show-message');
            return {
                layerCount: layers.length,
                toast: toast ? (toast.innerText || '').trim().substring(0, 60) : '',
            };
        }""")
        print(f"  After paste: {json.dumps(paste_check)}", flush=True)
    else:
        print("  Clipboard not ready — trying Cmd+V anyway", flush=True)
        page.mouse.click(700, 450)
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+v")
        page.wait_for_timeout(2000)

    ss(page, "P117_05_paste_test")

    # ============================================================
    #  STEP 7: Map the "Describe the desired image" bottom bar
    # ============================================================
    print("\n=== STEP 7: Bottom bar (Describe the desired image) ===", flush=True)

    bottom_bar = page.evaluate("""() => {
        // Find the bottom bar with "Describe the desired image"
        for (var el of document.querySelectorAll('[class*="chat-editor"], [class*="describe"], [class*="bottom-bar"]')) {
            var r = el.getBoundingClientRect();
            if (r.y > 800 && r.width > 300) {
                var children = [];
                for (var c of el.querySelectorAll('button, input, [contenteditable], [class*="icon"], [class*="btn"]')) {
                    var cr = c.getBoundingClientRect();
                    if (cr.width < 10) continue;
                    children.push({
                        tag: c.tagName,
                        class: (c.className || '').toString().substring(0, 40),
                        text: (c.innerText || '').trim().substring(0, 20),
                        x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                    });
                }

                return {
                    class: (el.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 100),
                    placeholder: el.getAttribute('placeholder') || '',
                    children: children,
                };
            }
        }
        return null;
    }""")

    print(f"  Bottom bar: {json.dumps(bottom_bar, indent=2)}", flush=True)

    # Credits
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 1000 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\n  Credits: {credits}", flush=True)

    ss(page, "P117_06_final")
    print(f"\n\n===== PHASE 117 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
