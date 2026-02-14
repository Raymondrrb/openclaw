"""Phase 88: More interactions.
1. Export dialog — check the screenshot (maybe it IS showing but not as high-z)
2. Chat editor — click individual option-labels to open dropdowns
3. CC panel — scroll to see Control Mode, aspect ratio, generate button
4. Image Editor Local Edit — click to open the sub-panel with mask tools
5. Generative Expand — click Expand to see its sub-panel
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


def dump_panel(page, label, limit=40):
    items = page.evaluate(f"""() => {{
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return [];
        var items = [];
        var seen = new Set();
        for (const el of p.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 8 && r.width < 300) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {{
                    var key = el.tagName + '|' + Math.round(r.y) + '|' + text;
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
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)
    return items


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
    #  PART 1: EXPORT — look at screenshot from P87
    #  The Export might be a popover or inline expansion, not a modal.
    #  Let's try: click Export, then scan ALL visible elements in the area.
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: EXPORT DIALOG (full scan)", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # First select a layer on canvas
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Click Export
    page.evaluate("() => document.querySelector('.c-export')?.click()")
    page.wait_for_timeout(2000)

    # Full page scan — every visible element
    export_scan = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            if (r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'
                && r.y > 30 && r.y < 500 && r.x > 900 && r.width < 400 && r.height < 60) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1) {
                    var key = text + '|' + Math.round(r.y) + '|' + Math.round(r.x);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 30),
                            z: parseInt(cs.zIndex) || 0,
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"\n  Export area scan ({len(export_scan)}):", flush=True)
    for e in export_scan:
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} z={e['z']} <{e['tag']}> c='{e['classes'][:22]}' '{e['text']}'", flush=True)
    ss(page, "P88_01_export")

    # Also check: is there a .c-export-panel or similar?
    export_classes = page.evaluate("""() => {
        var selectors = [
            '.c-export-panel', '.export-panel', '.export-popover',
            '.c-export-menu', '.export-dropdown', '.ant-popover',
            '.ant-dropdown', '[class*="popover"]', '[class*="dropdown"]',
        ];
        var results = [];
        for (var sel of selectors) {
            var els = document.querySelectorAll(sel);
            for (var el of els) {
                var r = el.getBoundingClientRect();
                var cs = window.getComputedStyle(el);
                results.push({
                    sel: sel,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    display: cs.display, visibility: cs.visibility,
                    classes: (el.className || '').toString().substring(0, 60),
                });
            }
        }
        return results;
    }""")
    print(f"\n  Export-related selectors ({len(export_classes)}):", flush=True)
    for e in export_classes:
        print(f"    {e['sel']} ({e['x']},{e['y']}) {e['w']}x{e['h']} d={e['display']} v={e['visibility']} c='{e['classes']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: CHAT EDITOR — CLICK OPTION LABELS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CHAT OPTION LABELS", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open chat editor
    page.mouse.click(628, 824)
    page.wait_for_timeout(2000)

    # Click the model label "Nano Banana Pro" directly
    page.evaluate("""() => {
        var labels = document.querySelectorAll('.option-label');
        for (var l of labels) {
            if ((l.innerText || '').trim() === 'Nano Banana Pro') {
                l.click(); return 'clicked';
            }
        }
        return 'not found';
    }""")
    page.wait_for_timeout(2000)
    ss(page, "P88_02_chat_model_label")

    # Check if a dropdown/selector appeared
    chat_dropdown = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        // Look for elements between the chat panel and the model label
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            // Check for new high-z or positioned elements near bottom
            if (r.y > 500 && r.y < 900 && r.width > 100 && r.height > 50
                && r.x > 300 && r.x < 1100 && z > 50) {
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
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"\n  Chat dropdown ({len(chat_dropdown)}):", flush=True)
    for c in chat_dropdown:
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} z={c['z']} <{c['tag']}> c='{c['classes'][:22]}' '{c['text']}'", flush=True)

    # Try clicking the chat-param div itself (the container with model name)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.mouse.click(628, 824)
    page.wait_for_timeout(1500)

    # Click chat-param
    clicked = page.evaluate("""() => {
        var param = document.querySelector('.chat-param');
        if (!param) return 'not found';
        var r = param.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    }""")
    print(f"\n  Chat param position: {clicked}", flush=True)

    if isinstance(clicked, dict):
        # Click directly on the param
        page.mouse.click(clicked['x'] + clicked['w'] // 2,
                         clicked['y'] + clicked['h'] // 2)
        page.wait_for_timeout(2000)
        ss(page, "P88_03_chat_param_click")

        # Check what appeared
        after = page.evaluate("""() => {
            var items = [];
            var seen = new Set();
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 150 && r.width > 100 && r.height > 50 && r.y > 400) {
                    for (var child of el.querySelectorAll('*')) {
                        var cr = child.getBoundingClientRect();
                        var text = (child.innerText || '').trim();
                        if (text.length > 0 && text.length < 50 && cr.width > 10
                            && cr.height > 8 && cr.height < 50
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
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
        }""")
        print(f"\n  After chat-param click ({len(after)}):", flush=True)
        for a in after:
            print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} z={a['z']} <{a['tag']}> c='{a['classes'][:22]}' '{a['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: CC PANEL — FULL SCROLL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CC PANEL FULL", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Character → Generate Images
    page.mouse.click(40, 766)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)
    page.mouse.click(40, 306)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Click Generate Images
    page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return;
        for (var el of p.querySelectorAll('p')) {
            if ((el.innerText || '').trim() === 'Generate Images') {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)
    dismiss_popups(page)

    # Scroll the CC panel down to see all options
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return;
        // Find scrollable container
        for (var child of p.querySelectorAll('*')) {
            if (child.scrollHeight > child.clientHeight + 50 && child.clientHeight > 200) {
                child.scrollTop = child.scrollHeight;
                return;
            }
        }
        p.scrollTop = p.scrollHeight;
    }""")
    page.wait_for_timeout(1000)
    ss(page, "P88_04_cc_scrolled")

    # Dump after scroll
    dump_panel(page, "CC Panel bottom")

    # Scroll back up to see top + dump all
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return;
        for (var child of p.querySelectorAll('*')) {
            if (child.scrollHeight > child.clientHeight + 50 && child.clientHeight > 200) {
                child.scrollTop = 0;
                return;
            }
        }
        p.scrollTop = 0;
    }""")
    page.wait_for_timeout(500)

    # Get ALL items with extended limit
    all_cc = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return [];
        var items = [];
        var seen = new Set();
        for (var child of p.querySelectorAll('*')) {
            var r = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 50 && r.width > 10 && r.height > 8
                && r.width < 300 && text.indexOf('\\n') === -1) {
                var key = child.tagName + '|' + text + '|' + Math.round(r.y);
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 40),
                        classes: (child.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 60);
    }""")
    print(f"\n  CC Panel all items ({len(all_cc)}):", flush=True)
    for item in all_cc:
        print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:22]}' '{item['text'][:35]}'", flush=True)

    # ============================================================
    #  PART 4: IMAGE EDITOR — LOCAL EDIT SUB-PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: LOCAL EDIT SUB-PANEL", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Image Editor
    page.mouse.click(40, 766)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Select a layer first
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Click Local Edit
    page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return;
        for (var btn of p.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Local Edit')) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P88_05_local_edit")

    # Check what panel opened
    le_panel = page.evaluate("""() => {
        var panels = [];
        var selectors = ['.c-gen-config.show', '.panels.show',
                         '.local-edit-panel', '[class*="local-edit"]',
                         '[class*="inpaint"]', '[class*="mask"]'];
        for (var sel of selectors) {
            var el = document.querySelector(sel);
            if (el) {
                var r = el.getBoundingClientRect();
                if (r.width > 50) {
                    var h5 = el.querySelector('h5');
                    panels.push({
                        sel: sel,
                        title: h5 ? (h5.innerText || '').trim() : '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 60),
                    });
                }
            }
        }
        return panels;
    }""")
    print(f"\n  Local Edit panels:", flush=True)
    for p in le_panel:
        print(f"    {p['sel']} title='{p['title']}' ({p['x']},{p['y']}) {p['w']}x{p['h']} c='{p['classes']}'", flush=True)

    # Dump the active panel
    dump_panel(page, "Local Edit panel")

    # ============================================================
    #  PART 5: EXPAND SUB-PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: EXPAND SUB-PANEL", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Image Editor again
    page.mouse.click(40, 766)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Click Expand
    page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return;
        for (var btn of p.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Expand')) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P88_06_expand")

    # Dump
    expand_panels = page.evaluate("""() => {
        var panels = [];
        var selectors = ['.c-gen-config.show', '.panels.show'];
        for (var sel of selectors) {
            var el = document.querySelector(sel);
            if (el) {
                var r = el.getBoundingClientRect();
                if (r.width > 50) {
                    var h5 = el.querySelector('h5');
                    panels.push({
                        sel: sel,
                        title: h5 ? (h5.innerText || '').trim() : '',
                        classes: (el.className || '').toString().substring(0, 60),
                    });
                }
            }
        }
        return panels;
    }""")
    print(f"\n  Expand panels:", flush=True)
    for p in expand_panels:
        print(f"    {p['sel']} title='{p['title']}' c='{p['classes']}'", flush=True)

    dump_panel(page, "Expand panel")

    print(f"\n\n===== PHASE 88 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
