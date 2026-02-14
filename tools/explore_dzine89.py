"""Phase 89: Pipeline-focused deep dive.
Focus areas for the Rayviews pipeline:
1. Img2Img — model selector, all available models, quality/aspect controls
2. CC — Select Ray, control modes (Camera/Pose/Reference), style selector
3. CC — Character Sheet panel (multi-angle)
4. Lip Sync — full panel with audio upload, mode selection
5. Face Swap — panel details for avatar consistency
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


def dump_panel(page, label, limit=50):
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
    title = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    cls = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (p) return (p.className || '').toString();
        var p2 = document.querySelector('.panels.show');
        return p2 ? (p2.className || '').toString() : 'NONE';
    }""")
    print(f"\n  {label} — title='{title}' class='{cls[:50]}' ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)
    return items


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
    return dump_panel(page, panel_name)


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
    #  PART 1: IMG2IMG — FULL MODEL LIST
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: IMG2IMG MODEL LIST", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Img2Img directly
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Check which panel opened
    i2i_check = page.evaluate("""() => {
        var cfg = document.querySelector('.c-gen-config.show');
        var panels = document.querySelector('.panels.show');
        return {
            cfg: cfg ? (cfg.className || '').toString().substring(0, 60) : null,
            cfg_title: cfg ? (cfg.querySelector('h5')?.innerText || '').trim() : null,
            panels: panels ? (panels.className || '').toString().substring(0, 60) : null,
            panels_title: panels ? (panels.querySelector('h5')?.innerText || '').trim() : null,
        };
    }""")
    print(f"  Panel check: {i2i_check}", flush=True)
    ss(page, "P89_01_img2img")

    # Img2Img uses c-gen-config with img2img-config-panel class
    # Open its style selector
    i2i_style_clicked = page.evaluate("""() => {
        // Find button.style inside c-gen-config (not panels.show which has Txt2Img)
        var cfg = document.querySelector('.c-gen-config.show');
        if (!cfg) return 'no cfg';
        var btn = cfg.querySelector('button.style');
        if (btn) {
            var r = btn.getBoundingClientRect();
            btn.click();
            return {clicked: true, x: Math.round(r.x), y: Math.round(r.y),
                    text: (btn.innerText || '').trim()};
        }
        return 'no button.style in cfg';
    }""")
    print(f"  Img2Img style click: {i2i_style_clicked}", flush=True)
    page.wait_for_timeout(2500)
    ss(page, "P89_02_img2img_style")

    # Check for style panel
    style_check = page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (!sp) return {found: false};
        var r = sp.getBoundingClientRect();
        if (r.width === 0) return {found: true, visible: false};

        var models = [];
        var seen = new Set();
        for (var el of sp.querySelectorAll('.item-name, .style-name')) {
            var text = (el.innerText || '').trim();
            if (text && !seen.has(text)) {
                seen.add(text);
                models.push(text);
            }
        }

        var cats = [];
        for (var el of sp.querySelectorAll('.category-item')) {
            var text = (el.innerText || '').trim();
            var sel = (el.className || '').includes('selected');
            cats.push({name: text, selected: sel});
        }

        return {
            found: true, visible: true,
            bounds: {x: Math.round(r.x), y: Math.round(r.y),
                     w: Math.round(r.width), h: Math.round(r.height)},
            categories: cats,
            models: models.slice(0, 40),
            modelCount: models.length,
        };
    }""")
    print(f"\n  Style panel: visible={style_check.get('visible')}, modelCount={style_check.get('modelCount')}", flush=True)
    if style_check.get('visible'):
        print(f"  Categories:", flush=True)
        for c in style_check.get('categories', []):
            sel = " [SELECTED]" if c['selected'] else ""
            print(f"    {c['name']}{sel}", flush=True)
        print(f"  Models ({style_check.get('modelCount', 0)}):", flush=True)
        for m in style_check.get('models', []):
            print(f"    {m}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: CC — SELECT RAY + FULL CONTROLS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CC WITH RAY", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Character panel
    open_panel(page, 40, 306, "Character")

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
    page.wait_for_timeout(2500)
    close_dialogs(page)
    dismiss_popups(page)

    # Select Ray character
    ray_selected = page.evaluate("""() => {
        // Look for Ray in the character list (right sidebar of CC panel)
        for (var el of document.querySelectorAll('button, .item')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                el.click();
                return 'clicked Ray button';
            }
        }
        // Try clicking by name span
        for (var el of document.querySelectorAll('.name')) {
            if ((el.innerText || '').trim() === 'Ray') {
                el.click();
                return 'clicked Ray name';
            }
        }
        return 'Ray not found';
    }""")
    print(f"  Ray selection: {ray_selected}", flush=True)
    page.wait_for_timeout(1500)
    ss(page, "P89_03_cc_ray")

    # Check if Ray is now selected
    ray_check = page.evaluate("""() => {
        var chooser = document.querySelector('.character-choose');
        if (chooser) {
            return (chooser.innerText || '').trim().substring(0, 40);
        }
        return null;
    }""")
    print(f"  Character chooser text: {ray_check}", flush=True)

    # Now try each Control Mode
    for mode in ['Camera', 'Pose', 'Reference']:
        page.evaluate(f"""() => {{
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return;
            for (var btn of p.querySelectorAll('button')) {{
                if ((btn.innerText || '').trim() === '{mode}') {{
                    btn.click(); return;
                }}
            }}
        }}""")
        page.wait_for_timeout(1500)

        # Get what changed
        mode_info = page.evaluate(f"""() => {{
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return null;
            // Find the selected option
            var selected = p.querySelector('.options.selected');
            var selectedText = selected ? (selected.innerText || '').trim() : 'none';
            // Check for camera/pose/reference-specific elements
            var extras = [];
            for (var child of p.querySelectorAll('*')) {{
                var r = child.getBoundingClientRect();
                var text = (child.innerText || '').trim();
                var cls = (child.className || '').toString();
                if (r.y > 350 && r.y < 550 && r.width > 10 && r.height > 8
                    && r.width < 300 && text.length > 0 && text.length < 40
                    && text.indexOf('\\n') === -1) {{
                    extras.push({{
                        text: text, y: Math.round(r.y),
                        classes: cls.substring(0, 25),
                    }});
                }}
            }}
            return {{selected: selectedText, extras: extras.slice(0, 10)}};
        }}""")
        print(f"\n  Mode '{mode}': {mode_info}", flush=True)
        ss(page, f"P89_04_cc_{mode.lower()}")

    # ============================================================
    #  PART 3: CHARACTER SHEET PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CHARACTER SHEET", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Character → Character Sheet
    open_panel(page, 40, 306, "Character")

    page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return;
        for (var el of p.querySelectorAll('p')) {
            if ((el.innerText || '').trim() === 'Character Sheet') {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2500)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P89_05_char_sheet")

    dump_panel(page, "Character Sheet")

    # ============================================================
    #  PART 4: LIP SYNC FULL PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: LIP SYNC", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Lip Sync
    open_panel(page, 40, 425, "Lip Sync")
    ss(page, "P89_06_lip_sync")

    # Check for upload areas and all controls
    ls_detail = page.evaluate("""() => {
        var p = document.querySelector('.lip-sync-operation-panel') ||
                document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var r = p.getBoundingClientRect();
        var items = [];
        var seen = new Set();
        for (var child of p.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            var cls = (child.className || '').toString();
            if (cr.width > 5 && cr.height > 5) {
                // Capture upload areas, buttons, inputs
                if (child.tagName === 'INPUT' || cls.includes('upload') ||
                    cls.includes('pick') || cls.includes('drag')) {
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 40) || '[upload area]',
                        classes: cls.substring(0, 35),
                        type: child.type || '',
                    });
                }
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1
                    && cr.width > 10 && cr.height > 8 && cr.width < 300) {
                    var key = child.tagName + '|' + Math.round(cr.y) + '|' + text;
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                            w: Math.round(cr.width), h: Math.round(cr.height),
                            text: text.substring(0, 40),
                            classes: cls.substring(0, 35),
                        });
                    }
                }
            }
        }
        return {
            bounds: {x: Math.round(r.x), y: Math.round(r.y),
                     w: Math.round(r.width), h: Math.round(r.height)},
            panelClass: (p.className || '').toString().substring(0, 60),
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 40),
        };
    }""")
    if ls_detail:
        print(f"  Lip Sync panel: {ls_detail['bounds']} class='{ls_detail['panelClass']}'", flush=True)
        print(f"  Items ({len(ls_detail.get('items', []))}):", flush=True)
        for item in ls_detail.get('items', []):
            tp = f" type={item.get('type', '')}" if item.get('type') else ''
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:25]}' '{item['text'][:30]}'{tp}", flush=True)

    # ============================================================
    #  PART 5: FACE SWAP PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: FACE SWAP", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Image Editor → Face Swap
    open_panel(page, 40, 698, "Image Editor")

    # Click Face Swap
    page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return;
        for (var btn of p.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Face Swap')) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P89_07_face_swap")

    dump_panel(page, "Face Swap")

    # ============================================================
    #  PART 6: EXPRESSION EDIT PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: EXPRESSION EDIT", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Image Editor → Expression Edit
    open_panel(page, 40, 698, "Image Editor")

    page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return;
        for (var btn of p.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Expression Edit')) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P89_08_expression")

    dump_panel(page, "Expression Edit")

    # ============================================================
    #  PART 7: INSERT CHARACTER PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 7: INSERT CHARACTER", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Character → Insert Character
    open_panel(page, 40, 306, "Character")

    page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return;
        for (var el of p.querySelectorAll('p')) {
            if ((el.innerText || '').trim() === 'Insert Character') {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2500)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P89_09_insert_char")

    dump_panel(page, "Insert Character")

    print(f"\n\n===== PHASE 89 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
