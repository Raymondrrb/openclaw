"""Phase 118: Image Editor sub-tools deep dive + Chat Editor panel.
P117 found: Image Editor has 8 sub-tools, clipboard paste works, bottom bar identified.

Goal: 1) Open each Image Editor sub-tool and map its panel/selectors
      2) Map Product Background sub-tool
      3) Open Chat Editor bottom bar panel and map it
      4) Try Enhance & Upscale on an existing result
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


def map_panel(page, label=""):
    """Capture current open panel state."""
    data = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').substring(0, 800);
        var title = panel.querySelector('h5, .panel-title, .title');

        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [class*="upload"], [class*="option"], [class*="slider"], [class*="switch"], [class*="select"], [contenteditable]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 15 || r.height < 8) continue;
            elements.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 35),
                type: el.type || '',
                disabled: el.disabled || false,
                placeholder: (el.placeholder || '').substring(0, 30),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        return {
            panelClass: (panel.className || '').toString().substring(0, 80),
            title: title ? (title.innerText || '').trim() : '',
            fullText: text,
            elements: elements.slice(0, 25),
        };
    }""")
    print(f"\n  [{label}] Panel: .{data.get('panelClass', '')[:60]}", flush=True)
    print(f"  Title: {data.get('title', '')}", flush=True)
    print(f"  Text:\n{data.get('fullText', '')[:400]}", flush=True)
    print(f"  Elements ({len(data.get('elements', []))}):", flush=True)
    for e in data.get('elements', []):
        d = " DISABLED" if e.get('disabled') else ""
        p = f" ph='{e['placeholder']}'" if e.get('placeholder') else ""
        print(f"    <{e['tag']}> .{e['cls'][:45]} '{e['text'][:28]}'{d}{p} ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)
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
    #  STEP 1: Image Editor -> Expression Edit sub-tool
    # ============================================================
    print("\n=== STEP 1: Image Editor -> Expression Edit ===", flush=True)

    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    # Click "Expression Edit" button inside the Image Editor panel
    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'Expression Edit') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Expression Edit: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    data = map_panel(page, "Expression Edit")
    ss(page, "P118_01_expression_edit_panel")

    # ============================================================
    #  STEP 2: Image Editor -> Face Swap sub-tool
    # ============================================================
    print("\n=== STEP 2: Image Editor -> Face Swap ===", flush=True)

    # Go back to Image Editor menu
    back_btn = page.evaluate("""() => {
        for (var b of document.querySelectorAll('button, [class*="back"]')) {
            var text = (b.innerText || '').trim();
            if (text === 'Back' || text.includes('←') || (b.className || '').includes('back')) {
                var r = b.getBoundingClientRect();
                if (r.width > 20 && r.x < 300) {
                    b.click();
                    return (b.className || '').toString().substring(0, 40);
                }
            }
        }
        // Try close icon
        var close = document.querySelector('.c-gen-config.show .ico-close');
        if (close) { close.click(); return 'closed'; }
        return false;
    }""")
    print(f"  Back: {back_btn}", flush=True)
    page.wait_for_timeout(1000)

    # Re-open Image Editor
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    # Click Face Swap
    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'Face Swap') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Face Swap: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    data = map_panel(page, "Face Swap")
    ss(page, "P118_02_face_swap_panel")

    # ============================================================
    #  STEP 3: Image Editor -> Local Edit sub-tool
    # ============================================================
    print("\n=== STEP 3: Image Editor -> Local Edit ===", flush=True)

    close_all_panels(page)
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'Local Edit') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Local Edit: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    data = map_panel(page, "Local Edit")
    ss(page, "P118_03_local_edit_panel")

    # ============================================================
    #  STEP 4: Image Editor -> Product Background sub-tool
    # ============================================================
    print("\n=== STEP 4: Image Editor -> Product Background ===", flush=True)

    close_all_panels(page)
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    # Product Background might be in a different section - scroll or find it
    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            var text = (b.innerText || '').trim();
            if (text.includes('Product') || text.includes('Background')) {
                b.click();
                return text;
            }
        }
        // Try scrolling the panel
        var panel = document.querySelector('.panels.show');
        if (panel) {
            panel.scrollTop = panel.scrollHeight;
        }
        return false;
    }""")
    print(f"  Clicked Product Background: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    data = map_panel(page, "Product Background")
    ss(page, "P118_04_product_background")

    # ============================================================
    #  STEP 5: Image Editor -> Expand sub-tool
    # ============================================================
    print("\n=== STEP 5: Image Editor -> Expand ===", flush=True)

    close_all_panels(page)
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1000)

    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            if ((b.innerText || '').trim() === 'Expand') {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Expand: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    data = map_panel(page, "Expand")
    ss(page, "P118_05_expand_panel")

    # ============================================================
    #  STEP 6: Chat Editor panel (click bottom bar open button)
    # ============================================================
    print("\n=== STEP 6: Chat Editor panel ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    # Click the open-chat-panel-btn at (830,818)
    page.mouse.click(830, 818)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Map the chat editor panel
    chat_panel = page.evaluate("""() => {
        // Find the chat editor panel (might be a popup or expanded bar)
        var panel = document.querySelector('.chat-editor-panel, .chat-panel, [class*="chat"][class*="panel"]');
        if (!panel) {
            // Try finding a large panel that appeared near bottom
            for (var el of document.querySelectorAll('[class*="chat"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 300 && r.height > 100 && r.y > 500) {
                    panel = el;
                    break;
                }
            }
        }
        if (!panel) return {error: 'no chat panel found'};

        var text = (panel.innerText || '').substring(0, 600);
        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [contenteditable], [class*="option"], [class*="model"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 15) continue;
            elements.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 35),
                type: el.type || '',
                placeholder: (el.placeholder || el.getAttribute('data-placeholder') || '').substring(0, 40),
                editable: el.getAttribute('contenteditable'),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        return {
            panelClass: (panel.className || '').toString().substring(0, 80),
            x: Math.round(panel.getBoundingClientRect().x),
            y: Math.round(panel.getBoundingClientRect().y),
            w: Math.round(panel.getBoundingClientRect().width),
            h: Math.round(panel.getBoundingClientRect().height),
            text: text,
            elements: elements.slice(0, 20),
        };
    }""")

    print(f"  Chat panel class: {chat_panel.get('panelClass', '')[:60]}", flush=True)
    if chat_panel.get('error'):
        print(f"  Error: {chat_panel['error']}", flush=True)
    else:
        print(f"  Position: ({chat_panel.get('x')},{chat_panel.get('y')}) {chat_panel.get('w')}x{chat_panel.get('h')}", flush=True)
        print(f"  Text:\n{chat_panel.get('text', '')[:400]}", flush=True)
        print(f"\n  Elements ({len(chat_panel.get('elements', []))}):", flush=True)
        for e in chat_panel.get('elements', []):
            ed = f" [editable={e['editable']}]" if e.get('editable') else ""
            ph = f" ph='{e['placeholder']}'" if e.get('placeholder') else ""
            print(f"    <{e['tag']}> .{e['cls'][:45]} '{e['text'][:28]}'{ed}{ph} ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P118_06_chat_editor")

    # ============================================================
    #  STEP 7: Chat Editor — model selector
    # ============================================================
    print("\n=== STEP 7: Chat Editor model selector ===", flush=True)

    # Find and click the model selector button
    model_btn = page.evaluate("""() => {
        // Look for option-btn or model selector in chat panel
        for (var el of document.querySelectorAll('button.option-btn, [class*="option-btn"], [class*="model-select"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 50 && r.y > 400) {
                return {
                    cls: (el.className || '').toString().substring(0, 50),
                    text: (el.innerText || '').trim().substring(0, 40),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                };
            }
        }
        return null;
    }""")
    print(f"  Model button: {json.dumps(model_btn)}", flush=True)

    if model_btn:
        page.mouse.click(model_btn['x'], model_btn['y'])
        page.wait_for_timeout(2000)

        # Map the model list
        models = page.evaluate("""() => {
            var items = document.querySelectorAll('.option-item, [class*="option-item"]');
            var list = [];
            for (var item of items) {
                var r = item.getBoundingClientRect();
                if (r.width < 50) continue;
                list.push({
                    text: (item.innerText || '').trim().substring(0, 40),
                    cls: (item.className || '').toString().substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    selected: (item.className || '').includes('selected') || (item.className || '').includes('active'),
                });
            }
            return list;
        }""")
        print(f"  Available models ({len(models)}):", flush=True)
        for m in models:
            sel = " [SELECTED]" if m.get('selected') else ""
            print(f"    '{m['text'][:35]}'{sel} ({m['x']},{m['y']})", flush=True)

        ss(page, "P118_07_chat_models")

        # Close model list
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  STEP 8: Enhance & Upscale panel (y=628)
    # ============================================================
    print("\n=== STEP 8: Enhance & Upscale ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    open_sidebar_tool(page, 628)
    data = map_panel(page, "Enhance & Upscale")
    ss(page, "P118_08_enhance_upscale")

    # ============================================================
    #  STEP 9: Motion Control panel (y=551)
    # ============================================================
    print("\n=== STEP 9: Motion Control ===", flush=True)

    open_sidebar_tool(page, 551)
    data = map_panel(page, "Motion Control")
    ss(page, "P118_09_motion_control")

    # ============================================================
    #  STEP 10: All sidebar tool icons — validate y positions
    # ============================================================
    print("\n=== STEP 10: Validate sidebar positions ===", flush=True)

    sidebar_icons = page.evaluate("""() => {
        var icons = [];
        var groups = document.querySelectorAll('.tool-group');
        for (var g of groups) {
            var r = g.getBoundingClientRect();
            // Get the label/tooltip
            var label = g.getAttribute('aria-label') || g.getAttribute('title') || '';
            // Get inner text from child elements
            var innerText = '';
            for (var c of g.querySelectorAll('span, [class*="text"], [class*="label"]')) {
                var t = (c.innerText || '').trim();
                if (t.length > 0 && t.length < 30) { innerText = t; break; }
            }
            // Get icon class
            var iconEl = g.querySelector('[class*="icon"], svg, img');
            var iconClass = iconEl ? (iconEl.className || '').toString().substring(0, 30) : '';

            icons.push({
                label: label || innerText,
                iconClass: iconClass,
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width),
                h: Math.round(r.height),
                active: (g.className || '').includes('active') || (g.className || '').includes('selected'),
            });
        }
        return icons;
    }""")

    print(f"  Sidebar tool groups ({len(sidebar_icons)}):", flush=True)
    for i, icon in enumerate(sidebar_icons):
        act = " [ACTIVE]" if icon.get('active') else ""
        print(f"    #{i+1} y={icon['y']} '{icon['label'][:25]}' .{icon['iconClass'][:25]}{act} w={icon['w']}", flush=True)

    # Credits final check
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

    ss(page, "P118_10_final")
    print(f"\n\n===== PHASE 118 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
