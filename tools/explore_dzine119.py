"""Phase 119: Chat Editor deep dive + Enhance/Upscale + download mechanism.
P118 found: Expression Edit sliders, Face Swap upload, Local Edit inpainting, Expand ratios.
Chat Editor didn't open properly, Enhance/Upscale returned empty.

Goal: 1) Properly open Chat Editor by clicking the prompt area at bottom
      2) Map Enhance & Upscale using panels.show specific selectors
      3) Download a result image and verify the mechanism
      4) Find the Insert Object and AI Eraser sub-tools
      5) Map what "Describe Canvas" / autoprompt does in Img2Img
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
DOWNLOAD_DIR = Path.home() / "Downloads"


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


def map_any_panel(page, label=""):
    """Capture any visible panel - both .c-gen-config and .panels types."""
    data = page.evaluate("""() => {
        var panels = [
            document.querySelector('.c-gen-config.show'),
            document.querySelector('.panels.show'),
            document.querySelector('.lip-sync-config-panel.show'),
        ].filter(p => p !== null);

        if (panels.length === 0) return {error: 'no panel visible'};

        var results = [];
        for (var panel of panels) {
            var text = (panel.innerText || '').substring(0, 1000);
            var elements = [];
            for (var el of panel.querySelectorAll('button, textarea, input, [class*="upload"], [class*="option"], [class*="slider"], [class*="switch"], [contenteditable], select, [class*="tab"], [class*="item"]')) {
                var r = el.getBoundingClientRect();
                if (r.width < 15 || r.height < 8) continue;
                // Skip if too many children (container element)
                if (el.children.length > 5) continue;
                elements.push({
                    tag: el.tagName,
                    cls: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 35),
                    type: el.type || '',
                    disabled: el.disabled || false,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
            results.push({
                panelClass: (panel.className || '').toString().substring(0, 80),
                x: Math.round(panel.getBoundingClientRect().x),
                y: Math.round(panel.getBoundingClientRect().y),
                w: Math.round(panel.getBoundingClientRect().width),
                h: Math.round(panel.getBoundingClientRect().height),
                fullText: text,
                elements: elements.slice(0, 30),
            });
        }
        return results;
    }""")

    if isinstance(data, dict) and data.get('error'):
        print(f"\n  [{label}] {data['error']}", flush=True)
        return data

    for panel in (data if isinstance(data, list) else [data]):
        print(f"\n  [{label}] Panel: .{panel.get('panelClass', '')[:60]}", flush=True)
        print(f"  Position: ({panel.get('x')},{panel.get('y')}) {panel.get('w')}x{panel.get('h')}", flush=True)
        print(f"  Text:\n{panel.get('fullText', '')[:500]}", flush=True)
        print(f"  Elements ({len(panel.get('elements', []))}):", flush=True)
        for e in panel.get('elements', []):
            d = " DISABLED" if e.get('disabled') else ""
            print(f"    <{e['tag']}> .{e['cls'][:45]} '{e['text'][:28]}'{d} ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)
    return data


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
    #  STEP 1: Chat Editor — click the prompt area directly
    # ============================================================
    print("\n=== STEP 1: Chat Editor — open via prompt click ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    # Find the contenteditable prompt in the bottom bar
    chat_prompt = page.evaluate("""() => {
        // Find chat editor bar elements
        var bar = document.querySelector('.chat-editor-bar-wrapper');
        if (!bar) return {error: 'no chat-editor-bar-wrapper'};

        var r = bar.getBoundingClientRect();
        var children = [];
        for (var el of bar.querySelectorAll('*')) {
            var cr = el.getBoundingClientRect();
            if (cr.width < 5 || cr.height < 5) continue;
            children.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 50),
                text: (el.innerText || '').trim().substring(0, 30),
                editable: el.getAttribute('contenteditable'),
                placeholder: (el.getAttribute('placeholder') || el.getAttribute('data-placeholder') || '').substring(0, 40),
                x: Math.round(cr.x), y: Math.round(cr.y),
                w: Math.round(cr.width), h: Math.round(cr.height),
            });
        }
        return {
            barPos: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
            children: children.slice(0, 15),
        };
    }""")
    print(f"  Bar: {json.dumps(chat_prompt.get('barPos'))}", flush=True)
    for c in chat_prompt.get('children', []):
        ed = f" [editable={c['editable']}]" if c.get('editable') else ""
        ph = f" ph='{c['placeholder']}'" if c.get('placeholder') else ""
        print(f"    <{c['tag']}> .{c['cls'][:40]} '{c['text'][:25]}'{ed}{ph} ({c['x']},{c['y']}) {c['w']}x{c['h']}", flush=True)

    # Click the "Describe the desired image" text area in the bottom bar
    # The bar is at ~(565,808) 310x68, so click center
    page.mouse.click(700, 830)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P119_01_chat_click")

    # Check if a larger panel opened
    chat_state = page.evaluate("""() => {
        // Look for expanded chat editor
        var panel = document.querySelector('.chat-editor-expand, .chat-panel-expand, [class*="chat-editor"][class*="expand"]');
        if (panel) {
            var r = panel.getBoundingClientRect();
            return {found: 'expand', cls: (panel.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
        }

        // Check if the bar itself expanded
        var bar = document.querySelector('.chat-editor-bar-wrapper');
        if (bar) {
            var r = bar.getBoundingClientRect();
            return {found: 'bar', cls: (bar.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
        }

        // Check for any new large overlay
        for (var el of document.querySelectorAll('[class*="chat"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 400 && r.height > 200 && r.y > 200) {
                return {found: 'overlay', cls: (el.className || '').toString().substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return {found: 'none'};
    }""")
    print(f"  After click: {json.dumps(chat_state)}", flush=True)

    # Now try clicking the open-chat-panel-btn (the expand icon)
    page.mouse.click(840, 828)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    chat_expanded = page.evaluate("""() => {
        // Broader search for any chat-related panel
        var results = [];
        for (var el of document.querySelectorAll('[class*="chat"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 200 && r.height > 100) {
                results.push({
                    cls: (el.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 100),
                });
            }
        }
        return results;
    }""")
    print(f"  Chat-related panels ({len(chat_expanded)}):", flush=True)
    for c in chat_expanded:
        print(f"    .{c['cls'][:50]} ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text'][:60]}'", flush=True)

    ss(page, "P119_02_chat_expanded")

    # ============================================================
    #  STEP 2: Enhance & Upscale — use .panels.show inner content
    # ============================================================
    print("\n=== STEP 2: Enhance & Upscale deep dive ===", flush=True)

    open_sidebar_tool(page, 628)

    # Direct DOM dump of the panels.show content
    eu_data = page.evaluate("""() => {
        var panel = document.querySelector('.panels.show');
        if (!panel) return {error: 'no panels.show'};

        var r = panel.getBoundingClientRect();
        var html = panel.innerHTML.substring(0, 2000);
        var text = (panel.innerText || '').substring(0, 800);

        // Get all interactive elements more broadly
        var elements = [];
        var allEls = panel.querySelectorAll('*');
        for (var el of allEls) {
            var cr = el.getBoundingClientRect();
            if (cr.width < 20 || cr.height < 15) continue;
            var tag = el.tagName;
            if (['BUTTON', 'INPUT', 'TEXTAREA', 'SELECT'].includes(tag) ||
                el.getAttribute('contenteditable') ||
                (el.className || '').toString().match(/tab|switch|option|slider|upload|item/i)) {
                elements.push({
                    tag: tag,
                    cls: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 35),
                    x: Math.round(cr.x), y: Math.round(cr.y),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                });
            }
        }

        return {
            pos: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
            text: text,
            elements: elements.slice(0, 25),
        };
    }""")

    if eu_data.get('error'):
        print(f"  Error: {eu_data['error']}", flush=True)
    else:
        print(f"  Position: {json.dumps(eu_data.get('pos'))}", flush=True)
        print(f"  Text:\n{eu_data.get('text', '')[:500]}", flush=True)
        print(f"  Elements ({len(eu_data.get('elements', []))}):", flush=True)
        for e in eu_data.get('elements', []):
            print(f"    <{e['tag']}> .{e['cls'][:45]} '{e['text'][:28]}' ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P119_03_enhance_upscale")

    # ============================================================
    #  STEP 3: Result image download test
    # ============================================================
    print("\n=== STEP 3: Download result image ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Results') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Find a result image URL
    result_urls = page.evaluate("""() => {
        var urls = [];
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        for (var img of imgs) {
            var r = img.getBoundingClientRect();
            if (r.width > 50 && r.y > 0 && r.y < 900) {
                urls.push({
                    src: img.src,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        return urls.slice(0, 5);
    }""")

    print(f"  Visible result images ({len(result_urls)}):", flush=True)
    for u in result_urls:
        print(f"    ({u['x']},{u['y']}) {u['w']}x{u['h']} {u['src'][:80]}...", flush=True)

    if result_urls:
        # Click first result to open preview
        first = result_urls[0]
        print(f"\n  Clicking first result image at ({first['x']},{first['y']})...", flush=True)
        page.mouse.click(first['x'], first['y'])
        page.wait_for_timeout(2000)

        # Check if preview opened
        preview = page.evaluate("""() => {
            var preview = document.querySelector('#result-preview');
            if (!preview) return {error: 'no preview'};
            var r = preview.getBoundingClientRect();
            var display = window.getComputedStyle(preview).display;
            var visibility = window.getComputedStyle(preview).visibility;

            // Find buttons in preview
            var btns = [];
            for (var b of preview.querySelectorAll('button')) {
                var br = b.getBoundingClientRect();
                if (br.width < 10) continue;
                btns.push({
                    cls: (b.className || '').toString().substring(0, 40),
                    text: (b.innerText || '').trim().substring(0, 20),
                    title: b.title || '',
                    x: Math.round(br.x), y: Math.round(br.y),
                    w: Math.round(br.width), h: Math.round(br.height),
                });
            }

            return {
                display: display, visibility: visibility,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                buttons: btns,
            };
        }""")

        print(f"  Preview: {json.dumps(preview, indent=2)}", flush=True)
        ss(page, "P119_04_result_preview")

        # Close preview
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # Try direct URL download
        test_url = first['src']
        print(f"\n  Testing direct URL fetch...", flush=True)

        # Use page.request to fetch the image
        try:
            response = page.evaluate("""(url) => {
                return new Promise((resolve) => {
                    fetch(url)
                        .then(r => r.blob())
                        .then(blob => {
                            resolve({
                                ok: true,
                                type: blob.type,
                                size: blob.size,
                            });
                        })
                        .catch(e => resolve({ok: false, error: e.message}));
                });
            }""", test_url)
            print(f"  Fetch result: {json.dumps(response)}", flush=True)
        except Exception as e:
            print(f"  Fetch error: {e}", flush=True)

    # ============================================================
    #  STEP 4: Image Editor -> Insert Object
    # ============================================================
    print("\n=== STEP 4: Image Editor -> Insert Object ===", flush=True)

    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'Insert Object') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Insert Object: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    map_any_panel(page, "Insert Object")
    ss(page, "P119_05_insert_object")

    # ============================================================
    #  STEP 5: Image Editor -> AI Eraser
    # ============================================================
    print("\n=== STEP 5: Image Editor -> AI Eraser ===", flush=True)

    close_all_panels(page)
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'AI Eraser') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked AI Eraser: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    map_any_panel(page, "AI Eraser")
    ss(page, "P119_06_ai_eraser")

    # ============================================================
    #  STEP 6: Image Editor -> Hand Repair
    # ============================================================
    print("\n=== STEP 6: Image Editor -> Hand Repair ===", flush=True)

    close_all_panels(page)
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'Hand Repair') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Hand Repair: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    map_any_panel(page, "Hand Repair")
    ss(page, "P119_07_hand_repair")

    # ============================================================
    #  STEP 7: Image Editor -> Face Repair
    # ============================================================
    print("\n=== STEP 7: Image Editor -> Face Repair ===", flush=True)

    close_all_panels(page)
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'Face Repair') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Face Repair: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    map_any_panel(page, "Face Repair")
    ss(page, "P119_08_face_repair")

    # ============================================================
    #  STEP 8: Img2Img "Describe Canvas" autoprompt
    # ============================================================
    print("\n=== STEP 8: Img2Img Describe Canvas ===", flush=True)

    open_sidebar_tool(page, 252)

    autoprompt = page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt.visible, button.autoprompt');
        if (!btn) {
            // Try broader search
            for (var b of document.querySelectorAll('button')) {
                if ((b.innerText || '').includes('Describe')) {
                    var r = b.getBoundingClientRect();
                    return {found: true, text: (b.innerText || '').trim(),
                            cls: (b.className || '').toString().substring(0, 50),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
            return {found: false};
        }
        var r = btn.getBoundingClientRect();
        return {found: true, text: (btn.innerText || '').trim(),
                cls: (btn.className || '').toString().substring(0, 50),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                visible: btn.offsetWidth > 0};
    }""")
    print(f"  Describe Canvas button: {json.dumps(autoprompt)}", flush=True)

    if autoprompt.get('found'):
        # Click it
        page.mouse.click(autoprompt['x'] + autoprompt['w']//2, autoprompt['y'] + autoprompt['h']//2)
        page.wait_for_timeout(5000)

        # Check what happened to the textarea
        prompt_after = page.evaluate("""() => {
            var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
            if (!ta) return {error: 'no textarea'};
            return {value: ta.value.substring(0, 200), length: ta.value.length};
        }""")
        print(f"  Prompt after autoprompt: {json.dumps(prompt_after)}", flush=True)

    ss(page, "P119_09_autoprompt")

    # Credits
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 100 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\n  Credits: {credits}", flush=True)

    ss(page, "P119_10_final")
    print(f"\n\n===== PHASE 119 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
