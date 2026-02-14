"""Phase 80: AI Video Camera controls (Key Frame mode), model selector dropdown,
Txt2Img full panel via .c-gen-config.show, and style-list-panel overlay.
Uses longer wait + smart load detection.
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


def wait_for_canvas(page, max_wait=30):
    """Wait for canvas to fully load (sidebar icons visible)."""
    for i in range(max_wait):
        loaded = page.evaluate("""() => {
            var tg = document.querySelectorAll('.tool-group');
            return tg.length;
        }""")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)  # Extra settle time
            return True
        page.wait_for_timeout(1000)
    print(f"  Canvas load timeout ({max_wait}s)", flush=True)
    return False


def dump_panel_show(page, label, limit=50):
    """Dump content of .panels.show container."""
    items = page.evaluate(f"""() => {{
        var p = document.querySelector('.panels.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        for (const el of p.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {{
                    items.push({{
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 40),
                        classes: (el.className || '').toString().substring(0, 35),
                    }});
                }}
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.tag + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    title = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"\n  {label} — title='{title}' ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text'][:35]}'", flush=True)
    return items


def dump_gen_config(page, label, limit=60):
    """Dump content of .c-gen-config.show container (Txt2Img only)."""
    items = page.evaluate(f"""() => {{
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        for (const el of p.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 400
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {{
                    items.push({{
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 50),
                        classes: (el.className || '').toString().substring(0, 40),
                    }});
                }}
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.tag + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    bounds = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        var r = p.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                classes: (p.className || '').toString().substring(0, 60)};
    }""")
    print(f"\n  {label} — bounds={bounds} ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text'][:40]}'", flush=True)
    return items


def open_panel(page, target_x, target_y, panel_name=""):
    """Open a sidebar tool with robust toggle + verification."""
    # Step 1: Click Storyboard (far away) to reset
    page.mouse.click(40, 766)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Step 2: Move mouse away to dismiss any tooltip
    page.mouse.move(700, 450)
    page.wait_for_timeout(500)

    # Step 3: Click the target tool
    page.mouse.click(target_x, target_y)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Step 4: Check if panel opened
    result = page.evaluate("""() => {
        var p1 = document.querySelector('.panels.show');
        var p2 = document.querySelector('.c-gen-config.show');
        var r1 = null, r2 = null;
        if (p1) {
            var r = p1.getBoundingClientRect();
            r1 = {type: 'panels.show', w: Math.round(r.width), h: Math.round(r.height),
                   visible: r.width > 100};
            var h5 = p1.querySelector('h5');
            r1.title = h5 ? (h5.innerText || '').trim() : '';
        }
        if (p2) {
            var r = p2.getBoundingClientRect();
            r2 = {type: 'c-gen-config.show', w: Math.round(r.width), h: Math.round(r.height),
                   visible: r.width > 100};
        }
        return {panels_show: r1, gen_config: r2};
    }""")
    print(f"  Panel check for '{panel_name}': {result}", flush=True)
    return result


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page, max_wait=40)
    close_dialogs(page)
    ss(page, "P80_00_loaded")

    # ============================================================
    #  PART 1: TXT2IMG — FULL PANEL VIA .c-gen-config.show
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: TXT2IMG FULL PANEL (.c-gen-config.show)", flush=True)
    print("=" * 60, flush=True)

    result = open_panel(page, 40, 197, "Txt2Img")
    ss(page, "P80_01_txt2img_panel")

    # Dump whichever container opened
    if result.get('gen_config') and result['gen_config'].get('visible'):
        dump_gen_config(page, "Txt2Img full panel")
    elif result.get('panels_show') and result['panels_show'].get('visible'):
        dump_panel_show(page, "Txt2Img via panels.show")
    else:
        # Try alternative: check for .c-gen-config without .show
        alt = page.evaluate("""() => {
            var configs = document.querySelectorAll('[class*="gen-config"]');
            var items = [];
            for (var c of configs) {
                var r = c.getBoundingClientRect();
                items.push({
                    classes: (c.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.width > 0,
                });
            }
            return items;
        }""")
        print(f"  Alt gen-config elements: {alt}", flush=True)

    # Get inputs/textareas from any panel
    inputs = page.evaluate("""() => {
        var containers = [
            document.querySelector('.c-gen-config.show'),
            document.querySelector('.c-gen-config'),
            document.querySelector('.panels.show'),
        ];
        for (var p of containers) {
            if (!p) continue;
            var r = p.getBoundingClientRect();
            if (r.width < 50) continue;
            var items = [];
            for (const el of p.querySelectorAll('input, textarea, select')) {
                var er = el.getBoundingClientRect();
                if (er.width > 10) {
                    items.push({
                        tag: el.tagName, type: el.type || '',
                        x: Math.round(er.x), y: Math.round(er.y),
                        w: Math.round(er.width), h: Math.round(er.height),
                        placeholder: (el.placeholder || '').substring(0, 40),
                        value: (el.value || '').substring(0, 40),
                    });
                }
            }
            if (items.length > 0) return items;
        }
        return [];
    }""")
    print(f"\n  Txt2Img inputs ({len(inputs)}):", flush=True)
    for inp in inputs:
        print(f"    ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']} type={inp['type']}> ph='{inp['placeholder']}' val='{inp['value']}'", flush=True)

    # ============================================================
    #  PART 2: TXT2IMG — STYLE/MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: TXT2IMG STYLE/MODEL SELECTOR", flush=True)
    print("=" * 60, flush=True)

    # Find model button in any visible container
    model_btn = page.evaluate("""() => {
        var selectors = ['.c-gen-config.show', '.c-gen-config', '.panels.show'];
        for (var sel of selectors) {
            var p = document.querySelector(sel);
            if (!p) continue;
            var btn = p.querySelector('.selected-btn-content');
            if (btn) {
                var r = btn.getBoundingClientRect();
                if (r.width > 0) {
                    return {selector: sel, text: (btn.innerText || '').trim().substring(0, 40),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
        }
        // Fallback: any .selected-btn-content visible
        var btn = document.querySelector('.selected-btn-content');
        if (btn) {
            var r = btn.getBoundingClientRect();
            if (r.width > 0) {
                return {selector: 'global', text: (btn.innerText || '').trim().substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    print(f"  Model button: {model_btn}", flush=True)

    if model_btn:
        page.mouse.click(model_btn['x'] + model_btn['w'] // 2,
                         model_btn['y'] + model_btn['h'] // 2)
        page.wait_for_timeout(2000)
        ss(page, "P80_02_model_selector")

        # Check for style-list-panel overlay
        style_panel = page.evaluate("""() => {
            var sp = document.querySelector('.style-list-panel');
            if (sp) {
                var r = sp.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        visible: r.width > 0,
                        classes: (sp.className || '').toString().substring(0, 50)};
            }
            return null;
        }""")
        print(f"  Style list panel: {style_panel}", flush=True)

        if style_panel and style_panel.get('visible'):
            # Dump categories and model names
            cats = page.evaluate("""() => {
                var sp = document.querySelector('.style-list-panel');
                if (!sp) return [];
                var items = [];
                var seen = new Set();
                for (const el of sp.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 35
                        && r.height > 10 && r.height < 45
                        && r.width > 20 && r.width < 250
                        && !seen.has(text)) {
                        seen.add(text);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 35),
                        });
                    }
                }
                return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 50);
            }""")
            print(f"\n  Style panel items ({len(cats)}):", flush=True)
            for c in cats:
                print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> '{c['text']}'", flush=True)
            ss(page, "P80_02b_style_panel_content")

        # Check high-z overlays
        overlays = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 200 && r.width > 200 && r.height > 200) {
                    items.push({
                        z: z, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 50),
                    });
                }
            }
            return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
        }""")
        print(f"\n  High-z overlays ({len(overlays)}):", flush=True)
        for o in overlays:
            print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']} c='{o['classes'][:40]}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: AI VIDEO — CAMERA CONTROLS IN KEY FRAME MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: AI VIDEO CAMERA CONTROLS (KEY FRAME)", flush=True)
    print("=" * 60, flush=True)

    result = open_panel(page, 40, 361, "AI Video")
    ss(page, "P80_03_ai_video")

    if result.get('panels_show') and result['panels_show'].get('visible'):
        dump_panel_show(page, "AI Video panel")

        # Make sure we're in Key Frame mode
        page.evaluate("""() => {
            var p = document.querySelector('.panels.show');
            if (!p) return;
            for (const btn of p.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Key Frame') {
                    btn.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(1500)

        # Look for Camera section by scrolling the panel and finding the Camera element
        # First scroll down in the panel
        panel_scroll = page.evaluate("""() => {
            var p = document.querySelector('.panels.show');
            if (!p) return null;
            // Find scrollable child
            for (const child of p.querySelectorAll('*')) {
                if (child.scrollHeight > child.clientHeight + 10) {
                    child.scrollTop = child.scrollHeight;
                    return {scrollHeight: child.scrollHeight, clientHeight: child.clientHeight,
                            tag: child.tagName, classes: (child.className || '').toString().substring(0, 40)};
                }
            }
            return 'no scrollable';
        }""")
        print(f"  Panel scroll: {panel_scroll}", flush=True)
        page.wait_for_timeout(500)

        # Now find Camera
        cam = page.evaluate("""() => {
            var p = document.querySelector('.panels.show');
            if (!p) return null;
            for (const el of p.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Camera') {
                    var r = el.getBoundingClientRect();
                    return {tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            classes: (el.className || '').toString().substring(0, 40),
                            parent_classes: (el.parentElement.className || '').toString().substring(0, 40)};
                }
            }
            return null;
        }""")
        print(f"  Camera element: {cam}", flush=True)

        if cam:
            # Click Camera
            page.mouse.click(cam['x'] + cam['w'] // 2, cam['y'] + cam['h'] // 2)
            page.wait_for_timeout(2000)
            ss(page, "P80_04_camera_clicked")

            # Check what appeared - look for any new popup or expanded area
            after_cam = page.evaluate("""() => {
                var items = [];
                // Check for popups
                for (const el of document.querySelectorAll('*')) {
                    var cs = window.getComputedStyle(el);
                    var z = parseInt(cs.zIndex) || 0;
                    var r = el.getBoundingClientRect();
                    if (z > 100 && r.width > 60 && r.height > 40 && r.x < 500) {
                        var text = (el.innerText || '').trim().replace(/\\n/g, ' | ').substring(0, 120);
                        if (text.length > 3) {
                            items.push({
                                z: z, tag: el.tagName,
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                classes: (el.className || '').toString().substring(0, 50),
                                text: text.substring(0, 80),
                            });
                        }
                    }
                }
                return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 8);
            }""")
            print(f"\n  After Camera click ({len(after_cam)}):", flush=True)
            for c in after_cam:
                print(f"    z={c['z']} ({c['x']},{c['y']}) {c['w']}x{c['h']} c='{c['classes'][:35]}' '{c['text'][:60]}'", flush=True)

            # Also check if Camera has a sibling dropdown that expanded
            cam_siblings = page.evaluate("""() => {
                var p = document.querySelector('.panels.show');
                if (!p) return [];
                var items = [];
                var found_cam = false;
                for (const el of p.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Camera') { found_cam = true; continue; }
                    if (found_cam) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 20 && r.height > 10 && r.width < 280) {
                            if (text.length > 0 && text.length < 40) {
                                items.push({
                                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    text: text,
                                    classes: (el.className || '').toString().substring(0, 30),
                                });
                            }
                        }
                        if (items.length >= 15) break;
                    }
                }
                return items;
            }""")
            print(f"\n  Elements after Camera ({len(cam_siblings)}):", flush=True)
            for s in cam_siblings:
                print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> '{s['text']}'", flush=True)

            # Maybe Camera is a toggle — try clicking its parent
            page.evaluate("""() => {
                var p = document.querySelector('.panels.show');
                if (!p) return;
                for (const el of p.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Camera') {
                        var parent = el.parentElement;
                        if (parent) parent.click();
                        return;
                    }
                }
            }""")
            page.wait_for_timeout(1500)
            ss(page, "P80_05_camera_parent")

            # Dump panel again to see if something expanded
            dump_panel_show(page, "AI Video after Camera parent click")

            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: AI VIDEO — MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: AI VIDEO MODEL SELECTOR", flush=True)
    print("=" * 60, flush=True)

    # Re-open AI Video
    result = open_panel(page, 40, 361, "AI Video (2)")

    # Find model selector
    av_model = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        var btn = p.querySelector('.selected-btn-content');
        if (btn) {
            var r = btn.getBoundingClientRect();
            return {text: (btn.innerText || '').trim().substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
        // Also try any element with model name
        for (const el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('Minimax') || text.includes('Hailuo'))
                && r.width > 50 && r.height > 10 && r.height < 50) {
                return {text: text.substring(0, 40), tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 30)};
            }
        }
        return null;
    }""")
    print(f"  AI Video model selector: {av_model}", flush=True)

    if av_model:
        page.mouse.click(av_model['x'] + av_model['w'] // 2,
                         av_model['y'] + av_model['h'] // 2)
        page.wait_for_timeout(2000)
        ss(page, "P80_06_model_dropdown")

        # Check what opened
        dropdown = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 200 && r.width > 100 && r.height > 60 && r.x < 500) {
                    var text = (el.innerText || '').trim().replace(/\\n/g, ' | ').substring(0, 120);
                    if (text.length > 5) {
                        items.push({
                            z: z, tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            classes: (el.className || '').toString().substring(0, 50),
                            text: text.substring(0, 100),
                        });
                    }
                }
            }
            return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
        }""")
        print(f"\n  Model dropdown ({len(dropdown)}):", flush=True)
        for d in dropdown:
            print(f"    z={d['z']} ({d['x']},{d['y']}) {d['w']}x{d['h']} c='{d['classes'][:35]}' '{d['text'][:80]}'", flush=True)

        if dropdown:
            dd = dropdown[0]
            model_opts = page.evaluate(f"""() => {{
                var items = [];
                var seen = new Set();
                for (const el of document.querySelectorAll('*')) {{
                    var r = el.getBoundingClientRect();
                    if (r.x >= {dd['x']} && r.x <= {dd['x'] + dd['w']}
                        && r.y >= {dd['y']} && r.y <= {dd['y'] + dd['h']}
                        && r.width > 20 && r.height > 10 && r.height < 50
                        && r.width < 250) {{
                        var text = (el.innerText || '').trim();
                        if (text.length > 2 && text.length < 35 && !seen.has(text)) {{
                            seen.add(text);
                            items.push({{
                                tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                text: text,
                                classes: (el.className || '').toString().substring(0, 30),
                            }});
                        }}
                    }}
                }}
                return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 20);
            }}""")
            print(f"\n  Model options ({len(model_opts)}):", flush=True)
            for m in model_opts:
                print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> c='{m['classes'][:20]}' '{m['text']}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: AI VIDEO SETTINGS (resolution, duration)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: AI VIDEO SETTINGS", flush=True)
    print("=" * 60, flush=True)

    # Re-open AI Video
    result = open_panel(page, 40, 361, "AI Video (3)")

    # Scroll down and find settings row
    page.mouse.move(200, 600)
    page.mouse.wheel(0, 200)
    page.wait_for_timeout(500)

    settings = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        for (const el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('768p') || text.includes('1080p'))
                && r.width > 50 && r.height > 10 && r.height < 40) {
                return {text: text, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 30)};
            }
        }
        return null;
    }""")
    print(f"  Settings element: {settings}", flush=True)

    if settings:
        page.mouse.click(settings['x'] + settings['w'] // 2,
                         settings['y'] + settings['h'] // 2)
        page.wait_for_timeout(2000)
        ss(page, "P80_07_settings_dropdown")

        # Dump popup
        popup = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 100 && r.width > 80 && r.height > 50 && r.x < 500 && r.y > 50) {
                    var text = (el.innerText || '').trim().replace(/\\n/g, ' | ').substring(0, 150);
                    if (text.length > 3) {
                        items.push({
                            z: z, tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            classes: (el.className || '').toString().substring(0, 50),
                            text: text.substring(0, 120),
                        });
                    }
                }
            }
            return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
        }""")
        print(f"\n  Settings popup ({len(popup)}):", flush=True)
        for p_ in popup:
            print(f"    z={p_['z']} ({p_['x']},{p_['y']}) {p_['w']}x{p_['h']} '{p_['text'][:100]}'", flush=True)

        if popup:
            sp = popup[0]
            opts = page.evaluate(f"""() => {{
                var items = [];
                var seen = new Set();
                for (const el of document.querySelectorAll('*')) {{
                    var r = el.getBoundingClientRect();
                    if (r.x >= {sp['x']} && r.x <= {sp['x'] + sp['w']}
                        && r.y >= {sp['y']} && r.y <= {sp['y'] + sp['h']}
                        && r.width > 15 && r.height > 8 && r.height < 40
                        && r.width < 200) {{
                        var text = (el.innerText || '').trim();
                        if (text.length > 0 && text.length < 30 && !seen.has(text)) {{
                            seen.add(text);
                            items.push({{
                                tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                text: text,
                            }});
                        }}
                    }}
                }}
                return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 25);
            }}""")
            print(f"\n  Settings options ({len(opts)}):", flush=True)
            for o in opts:
                print(f"    ({o['x']},{o['y']}) {o['w']}x{o['h']} <{o['tag']}> '{o['text']}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 6: TXT2IMG ADVANCED POPUP DEEP DIVE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: TXT2IMG ADVANCED POPUP", flush=True)
    print("=" * 60, flush=True)

    result = open_panel(page, 40, 197, "Txt2Img (2)")

    # Click Advanced
    adv = page.evaluate("""() => {
        // Try both containers
        var containers = [
            document.querySelector('.c-gen-config.show'),
            document.querySelector('.c-gen-config'),
            document.querySelector('.panels.show'),
        ];
        for (var p of containers) {
            if (!p) continue;
            for (const el of p.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Advanced' && r.width > 30 && r.height > 15) {
                    el.click();
                    return {x: Math.round(r.x), y: Math.round(r.y), tag: el.tagName,
                            container: (p.className || '').toString().substring(0, 30)};
                }
            }
        }
        // Fallback: search whole page for Advanced button
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x < 400 && r.y > 300 && r.width > 30 && r.height > 15) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), tag: el.tagName,
                        container: 'global'};
            }
        }
        return null;
    }""")
    print(f"  Advanced clicked: {adv}", flush=True)
    page.wait_for_timeout(2000)
    ss(page, "P80_08_advanced")

    # Dump advanced area — comprehensive search
    adv_items = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        // Look for high-z popup
        var containers = [];
        for (const el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 50 && r.width > 100 && r.height > 100 && r.x < 500 && r.y > 50) {
                containers.push({el: el, z: z, w: r.width, h: r.height});
            }
        }
        containers.sort(function(a,b) { return b.z - a.z; });
        // Use highest-z container
        var target = containers.length > 0 ? containers[0].el : null;
        if (!target) return [];
        for (const child of target.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 45 && cr.height > 8 && cr.height < 50
                && cr.width > 10 && cr.width < 300) {
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
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"\n  Advanced popup items ({len(adv_items)}):", flush=True)
    for a in adv_items:
        print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> c='{a['classes'][:22]}' '{a['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    print(f"\n\n===== PHASE 80 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
