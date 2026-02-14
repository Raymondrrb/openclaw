"""Phase 84: Final gaps.
1. Enhance & Upscale — Video mode
2. Video Editor model selector
3. Video Editor Advanced popup
4. Export dialog full mapping
5. Img2Img model selector (Nano Banana Pro list)
6. Chat Editor Bar interaction
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


def open_panel(page, target_x, target_y, panel_name=""):
    page.mouse.click(40, 766)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(500)
    page.mouse.click(target_x, target_y)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    title = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"  Opened '{panel_name}': title='{title}'", flush=True)
    return title


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


def dump_panel(page, label, limit=50):
    items = page.evaluate(f"""() => {{
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        var seen = new Set();
        for (const el of p.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {{
                    var key = el.tagName + '|' + Math.round(r.x) + '|' + Math.round(r.y);
                    if (!seen.has(key)) {{
                        seen.add(key);
                        items.push({{
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                        }});
                    }}
                }}
            }}
        }}
        return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    title = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"\n  {label} — title='{title}' ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)
    return items


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  PART 1: ENHANCE & UPSCALE — VIDEO MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: ENHANCE & UPSCALE VIDEO MODE", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 627, "Enhance & Upscale")
    dismiss_popups(page)

    # Click Video tab
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        for (var btn of p.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Video') { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(1500)
    ss(page, "P84_01_enhance_video")
    dump_panel(page, "Enhance Video mode")

    # ============================================================
    #  PART 2: VIDEO EDITOR MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: VIDEO EDITOR MODELS", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 490, "Video Editor")
    dismiss_popups(page)

    # Click model selector
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        var btn = p.querySelector('.selected-btn-content');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)
    dismiss_popups(page)
    ss(page, "P84_02_video_editor_models")

    # Get model list
    ve_models = page.evaluate("""() => {
        var sp = document.querySelector('.selector-panel');
        if (!sp) return [];
        var items = [];
        var names = sp.querySelectorAll('.item-name');
        for (var name of names) {
            var text = (name.innerText || '').trim();
            var parent = name.closest('.style-item') || name.parentElement;
            var desc = parent ? parent.querySelector('.item-desc') : null;
            var descText = desc ? (desc.innerText || '').trim() : '';
            var labels = parent ? parent.querySelector('.item-labels') : null;
            var labelText = labels ? (labels.innerText || '').trim() : '';
            var hot = parent ? parent.querySelector('.item-hot') : null;
            var selected = parent ? (parent.className || '').includes('selected') : false;
            items.push({
                name: text, credits: descText, labels: labelText,
                hot: hot ? true : false, selected: selected,
            });
        }
        return items;
    }""")
    print(f"\n  Video Editor models ({len(ve_models)}):", flush=True)
    for m in ve_models:
        flags = []
        if m['hot']: flags.append('HOT')
        if m['selected']: flags.append('SELECTED')
        flag_str = f" [{', '.join(flags)}]" if flags else ''
        print(f"    {m['name']} — {m['credits']} | {m['labels']}{flag_str}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: VIDEO EDITOR ADVANCED
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: VIDEO EDITOR ADVANCED", flush=True)
    print("=" * 60, flush=True)

    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        var btn = p.querySelector('.advanced-btn');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1500)
    ss(page, "P84_03_ve_advanced")

    adv = page.evaluate("""() => {
        var el = document.querySelector('.advanced-content.show') ||
                 document.querySelector('.advanced-content');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        var items = [];
        var seen = new Set();
        for (var child of el.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 40 && cr.width > 10 && cr.height > 8) {
                var key = text + '|' + Math.round(cr.y);
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text,
                        classes: (child.className || '').toString().substring(0, 25),
                    });
                }
            }
        }
        return {
            bounds: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20),
        };
    }""")
    if adv:
        print(f"  Advanced bounds: {adv['bounds']}", flush=True)
        print(f"  Advanced items ({len(adv['items'])}):", flush=True)
        for a in adv['items']:
            print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> '{a['text']}'", flush=True)
    else:
        print("  Advanced: null", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: EXPORT DIALOG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: EXPORT DIALOG", flush=True)
    print("=" * 60, flush=True)

    # Click Export button in header
    page.evaluate("""() => {
        var btn = document.querySelector('.c-export');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)
    ss(page, "P84_04_export")

    # Dump export dialog
    export = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 200 && r.height > 200 && r.x > 200) {
                // Found the export dialog
                for (var child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    if (text.length > 0 && text.length < 40 && cr.width > 15
                        && cr.height > 8 && cr.height < 50 && cr.width < 300) {
                        var key = text + '|' + Math.round(cr.y);
                        if (!seen.has(key)) {
                            seen.add(key);
                            items.push({
                                tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                                w: Math.round(cr.width), h: Math.round(cr.height),
                                text: text,
                                classes: (child.className || '').toString().substring(0, 30),
                            });
                        }
                    }
                }
                break;
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"\n  Export dialog ({len(export)}):", flush=True)
    for e in export:
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> c='{e['classes'][:22]}' '{e['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: IMG2IMG MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: IMG2IMG MODEL SELECTOR", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 252, "Img2Img")
    dismiss_popups(page)

    # Click style button
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        var btn = p.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)
    ss(page, "P84_05_img2img_styles")

    # Check for style panel
    i2i_panel = page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (sp) {
            var r = sp.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height), visible: r.width > 0};
        }
        return null;
    }""")
    print(f"  Img2Img style panel: {i2i_panel}", flush=True)

    if i2i_panel and i2i_panel.get('visible'):
        # Get categories
        cats = page.evaluate("""() => {
            var sp = document.querySelector('.style-list-panel');
            if (!sp) return [];
            var items = [];
            var seen = new Set();
            for (var el of sp.querySelectorAll('.category-item')) {
                var text = (el.innerText || '').trim();
                if (!seen.has(text)) {
                    seen.add(text);
                    items.push(text);
                }
            }
            return items;
        }""")
        print(f"\n  Img2Img style categories: {cats}", flush=True)

        # Get visible styles
        styles = page.evaluate("""() => {
            var sp = document.querySelector('.style-list-panel');
            if (!sp) return [];
            var items = [];
            var names = sp.querySelectorAll('.item-name, .style-name');
            for (var n of names) {
                var text = (n.innerText || '').trim();
                items.push(text);
            }
            return items.slice(0, 30);
        }""")
        print(f"  Visible styles ({len(styles)}): {styles[:15]}...", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 6: CHAT EDITOR BAR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: CHAT EDITOR BAR", flush=True)
    print("=" * 60, flush=True)

    # The chat editor bar is always at the bottom
    chat = page.evaluate("""() => {
        var bar = document.querySelector('.chat-editor-bar-wrapper');
        if (!bar) return null;
        var r = bar.getBoundingClientRect();
        var items = [];
        for (var child of bar.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 40 && cr.width > 10 && cr.height > 8) {
                items.push({
                    tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                    text: text,
                    classes: (child.className || '').toString().substring(0, 30),
                });
            }
        }
        // Also get inputs
        for (var inp of bar.querySelectorAll('input, textarea')) {
            var ir = inp.getBoundingClientRect();
            items.push({
                tag: inp.tagName, type: inp.type || 'textarea',
                x: Math.round(ir.x), y: Math.round(ir.y),
                w: Math.round(ir.width), h: Math.round(ir.height),
                placeholder: (inp.placeholder || '').substring(0, 40),
                classes: (inp.className || '').toString().substring(0, 30),
            });
        }
        return {
            bounds: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
            items: items,
        };
    }""")
    if chat:
        print(f"  Chat bar bounds: {chat['bounds']}", flush=True)
        print(f"  Chat bar items ({len(chat['items'])}):", flush=True)
        for c in chat['items']:
            extra = f" ph='{c.get('placeholder', '')}'" if c.get('placeholder') else ''
            print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:22]}' '{c.get('text', '')}'{extra}", flush=True)
    else:
        print("  Chat bar: null", flush=True)

    # Click the chat bar to expand it
    if chat:
        page.mouse.click(chat['bounds']['x'] + chat['bounds']['w'] // 2,
                         chat['bounds']['y'] + chat['bounds']['h'] // 2)
        page.wait_for_timeout(1500)
        ss(page, "P84_06_chat_expanded")

        # Check for expanded chat interface
        chat_expanded = page.evaluate("""() => {
            var items = [];
            var seen = new Set();
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 500 && r.width > 200 && r.height > 100 && r.y > 300) {
                    for (var child of el.querySelectorAll('*')) {
                        var cr = child.getBoundingClientRect();
                        var text = (child.innerText || '').trim();
                        if (text.length > 0 && text.length < 40 && cr.width > 15
                            && cr.height > 8 && cr.height < 50) {
                            var key = text + '|' + Math.round(cr.y);
                            if (!seen.has(key)) {
                                seen.add(key);
                                items.push({
                                    tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                                    text: text,
                                    classes: (child.className || '').toString().substring(0, 25),
                                });
                            }
                        }
                    }
                    break;
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"\n  Chat expanded ({len(chat_expanded)}):", flush=True)
        for c in chat_expanded:
            print(f"    ({c['x']},{c['y']}) <{c['tag']}> c='{c['classes'][:20]}' '{c['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    print(f"\n\n===== PHASE 84 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
