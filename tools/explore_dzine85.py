"""Phase 85: Clean capture of remaining gaps.
1. Export dialog — close ALL overlays first, then click Export
2. Chat Editor Bar — click the INPUT element directly, type prompt, check expansion
3. Img2Img style/model selector — ensure panel is fully open before clicking style
4. Txt2Img model list (complete catalog of available image models)
5. Header bar — project name, zoom, credits, all buttons
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
    """Close any stale selector panels, popups, overlays."""
    # Press Escape multiple times
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

    # Close any visible selector panels
    page.evaluate("""() => {
        var panels = document.querySelectorAll('.selector-panel, .style-list-panel');
        for (var p of panels) {
            var r = p.getBoundingClientRect();
            if (r.width > 0) {
                // Click outside to dismiss
                document.body.click();
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Close any gen-config panels
    page.evaluate("""() => {
        var close = document.querySelector('.c-gen-config.show .ico-close');
        if (close) close.click();
    }""")
    page.wait_for_timeout(500)

    close_dialogs(page)

    # Click canvas center to deselect everything
    page.mouse.click(700, 450)
    page.wait_for_timeout(500)


def open_panel(page, target_x, target_y, panel_name=""):
    page.mouse.click(40, 766)  # Storyboard (distant toggle)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)  # Move away to dismiss tooltip
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


def dump_high_z(page, label, min_z=500, limit=50):
    """Dump elements with high z-index (dialogs, overlays)."""
    items = page.evaluate(f"""() => {{
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {{
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > {min_z} && r.width > 100 && r.height > 50) {{
                // Found a high-z container, dump its children
                for (var child of el.querySelectorAll('*')) {{
                    var cr = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    if (text.length > 0 && text.length < 60 && cr.width > 10
                        && cr.height > 8 && cr.height < 60 && cr.width < 400
                        && text.indexOf('\\n') === -1) {{
                        var key = text + '|' + Math.round(cr.y);
                        if (!seen.has(key)) {{
                            seen.add(key);
                            items.push({{
                                tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                                w: Math.round(cr.width), h: Math.round(cr.height),
                                text: text.substring(0, 50),
                                classes: (child.className || '').toString().substring(0, 30),
                                z: z,
                            }});
                        }}
                    }}
                }}
                break;
            }}
        }}
        return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} z={el['z']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)
    return items


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # ---- CLEANUP: Close all extra Dzine tabs ----
    pages = ctx.pages
    print(f"  Found {len(pages)} open tabs", flush=True)
    dzine_pages = [p for p in pages if "dzine.ai" in (p.url or "")]
    print(f"  Dzine tabs: {len(dzine_pages)}", flush=True)
    # Keep only one Dzine tab, close the rest
    kept = False
    for p in pages:
        url = p.url or ""
        if "dzine.ai" in url:
            if kept:
                print(f"  Closing: {url[:60]}", flush=True)
                try:
                    p.close()
                except Exception:
                    pass
            else:
                kept = True
                print(f"  Keeping: {url[:60]}", flush=True)
        # Also close blank/empty tabs created by previous explore scripts
        elif url in ("", "about:blank", "chrome://newtab/"):
            print(f"  Closing blank tab", flush=True)
            try:
                p.close()
            except Exception:
                pass

    pages_after = ctx.pages
    print(f"  Tabs after cleanup: {len(pages_after)}", flush=True)

    # ---- Now open a fresh canvas tab ----
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  PART 1: EXPORT DIALOG (clean capture)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: EXPORT DIALOG", flush=True)
    print("=" * 60, flush=True)

    # Make sure nothing is open
    close_all_overlays(page)
    page.wait_for_timeout(1000)

    # Find and click Export button by class
    export_clicked = page.evaluate("""() => {
        // Try .c-export class first
        var btn = document.querySelector('.c-export');
        if (btn) { btn.click(); return 'c-export'; }
        // Try text-based
        for (var el of document.querySelectorAll('button, div')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Export' && r.y < 60 && r.x > 1200) {
                el.click(); return 'text:' + Math.round(r.x) + ',' + Math.round(r.y);
            }
        }
        return null;
    }""")
    print(f"  Export click: {export_clicked}", flush=True)
    page.wait_for_timeout(2000)
    ss(page, "P85_01_export_clean")

    # Dump the export dialog
    export_items = dump_high_z(page, "Export Dialog")

    # Also try to find it by specific classes
    export_detail = page.evaluate("""() => {
        // Look for export-specific elements
        var results = {};
        // File type buttons
        var types = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (['JPG', 'PNG', 'SVG', 'PSD'].includes(text) && r.y > 100 && r.height < 40 && r.width < 80) {
                var selected = (el.className || '').includes('selected') || (el.className || '').includes('active');
                types.push({text: text, selected: selected, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        results.fileTypes = types;

        // Upscale options
        var scales = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (['1x', '1.5x', '2x', '3x', '4x'].includes(text) && r.y > 100 && r.height < 40) {
                var selected = (el.className || '').includes('selected') || (el.className || '').includes('active');
                scales.push({text: text, selected: selected, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        results.scales = scales;

        // Buttons
        var buttons = [];
        for (var btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (r.y > 100 && r.height > 20 && r.width > 100
                && (text.includes('Export') || text.includes('download') || text.includes('Zip'))) {
                buttons.push({text: text, x: Math.round(r.x), y: Math.round(r.y),
                              w: Math.round(r.width), h: Math.round(r.height),
                              classes: (btn.className || '').toString().substring(0, 30)});
            }
        }
        results.buttons = buttons;

        return results;
    }""")
    print(f"\n  Export file types: {export_detail.get('fileTypes', [])}", flush=True)
    print(f"  Export scales: {export_detail.get('scales', [])}", flush=True)
    print(f"  Export buttons: {export_detail.get('buttons', [])}", flush=True)

    # Close export
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: CHAT EDITOR BAR (full interaction)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CHAT EDITOR BAR", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Find the chat editor bar and its input
    chat_info = page.evaluate("""() => {
        var bar = document.querySelector('.chat-editor-bar') ||
                  document.querySelector('.chat-editor-bar-wrapper');
        if (!bar) return null;
        var r = bar.getBoundingClientRect();
        var result = {
            bounds: {x: Math.round(r.x), y: Math.round(r.y),
                     w: Math.round(r.width), h: Math.round(r.height)},
            class: (bar.className || '').toString(),
        };

        // Find input/textarea inside
        var inputs = [];
        for (var inp of bar.querySelectorAll('input, textarea, [contenteditable]')) {
            var ir = inp.getBoundingClientRect();
            inputs.push({
                tag: inp.tagName, type: inp.type || '',
                contentEditable: inp.contentEditable,
                x: Math.round(ir.x), y: Math.round(ir.y),
                w: Math.round(ir.width), h: Math.round(ir.height),
                placeholder: (inp.placeholder || inp.getAttribute('data-placeholder') || '').substring(0, 50),
                classes: (inp.className || '').toString().substring(0, 30),
            });
        }
        result.inputs = inputs;

        // Find clickable children
        var children = [];
        for (var child of bar.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (cr.width > 5 && cr.height > 5 && (text.length > 0 || child.tagName === 'INPUT'
                || child.tagName === 'BUTTON' || child.tagName === 'SVG')) {
                children.push({
                    tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                    text: text.substring(0, 30),
                    classes: (child.className || '').toString().substring(0, 25),
                });
            }
        }
        result.children = children.slice(0, 20);
        return result;
    }""")

    if chat_info:
        print(f"  Chat bar: {chat_info['bounds']} class='{chat_info['class']}'", flush=True)
        print(f"  Inputs ({len(chat_info.get('inputs', []))}):", flush=True)
        for inp in chat_info.get('inputs', []):
            print(f"    <{inp['tag']}> type={inp.get('type','')} ce={inp.get('contentEditable','')} "
                  f"({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} ph='{inp.get('placeholder','')}'", flush=True)
        print(f"  Children ({len(chat_info.get('children', []))}):", flush=True)
        for ch in chat_info.get('children', []):
            print(f"    ({ch['x']},{ch['y']}) {ch['w']}x{ch['h']} <{ch['tag']}> c='{ch['classes'][:20]}' '{ch['text'][:25]}'", flush=True)

        # Try clicking the input area directly
        if chat_info.get('inputs'):
            inp = chat_info['inputs'][0]
            page.mouse.click(inp['x'] + inp['w'] // 2, inp['y'] + inp['h'] // 2)
        else:
            # Click the bar text area
            page.mouse.click(chat_info['bounds']['x'] + 100,
                             chat_info['bounds']['y'] + chat_info['bounds']['h'] // 2)
        page.wait_for_timeout(1500)
        ss(page, "P85_02_chat_clicked")

        # Check if anything expanded
        expanded = page.evaluate("""() => {
            // Check for any new high-z overlay near bottom
            var found = [];
            for (var el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 100 && r.width > 200 && r.height > 80 && r.y > 400) {
                    found.push({
                        tag: el.tagName, z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 50),
                    });
                }
            }
            // Also check if chat bar changed size
            var bar = document.querySelector('.chat-editor-bar') ||
                      document.querySelector('.chat-editor-bar-wrapper');
            var barSize = null;
            if (bar) {
                var r = bar.getBoundingClientRect();
                barSize = {x: Math.round(r.x), y: Math.round(r.y),
                           w: Math.round(r.width), h: Math.round(r.height)};
            }
            return {overlays: found.slice(0, 5), barSize: barSize};
        }""")
        print(f"\n  After click — bar size: {expanded.get('barSize')}", flush=True)
        print(f"  Overlays ({len(expanded.get('overlays', []))}):", flush=True)
        for o in expanded.get('overlays', []):
            print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']} <{o['tag']}> c='{o['classes']}'", flush=True)

        # Try typing something to see if the chat mode activates
        page.keyboard.type("test prompt", delay=30)
        page.wait_for_timeout(1000)
        ss(page, "P85_03_chat_typed")

        # Check what happened
        chat_after = page.evaluate("""() => {
            var bar = document.querySelector('.chat-editor-bar') ||
                      document.querySelector('.chat-editor-bar-wrapper');
            if (!bar) return null;
            var r = bar.getBoundingClientRect();
            // Check for text content
            var inputs = [];
            for (var inp of bar.querySelectorAll('input, textarea, [contenteditable]')) {
                var ir = inp.getBoundingClientRect();
                inputs.push({
                    tag: inp.tagName, value: (inp.value || inp.innerText || '').substring(0, 50),
                    w: Math.round(ir.width), h: Math.round(ir.height),
                });
            }
            return {
                bounds: {x: Math.round(r.x), y: Math.round(r.y),
                         w: Math.round(r.width), h: Math.round(r.height)},
                inputs: inputs,
                allText: (bar.innerText || '').substring(0, 100),
            };
        }""")
        print(f"\n  After typing: {chat_after}", flush=True)

    else:
        print("  Chat bar: NOT FOUND", flush=True)

    # Clear and escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: IMG2IMG STYLE/MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: IMG2IMG STYLE SELECTOR", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Img2Img panel
    open_panel(page, 40, 252, "Img2Img")
    dismiss_popups(page)
    page.wait_for_timeout(1000)

    # Verify it's the right panel
    panel_title = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return 'NO .panels.show';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"  Panel title: {panel_title}", flush=True)

    # Find the model/style button in the Img2Img panel
    i2i_model = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        // Find button.style or selected-btn-content
        var style_btn = p.querySelector('button.style');
        var selected = p.querySelector('.selected-btn-content');
        var results = {};
        if (style_btn) {
            var r = style_btn.getBoundingClientRect();
            results.style_btn = {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (style_btn.innerText || '').trim().substring(0, 30),
                classes: (style_btn.className || '').toString().substring(0, 30),
            };
        }
        if (selected) {
            var r = selected.getBoundingClientRect();
            results.selected_btn = {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (selected.innerText || '').trim().substring(0, 30),
                classes: (selected.className || '').toString().substring(0, 30),
            };
        }
        return results;
    }""")
    print(f"  Img2Img model buttons: {i2i_model}", flush=True)
    ss(page, "P85_04_img2img_panel")

    # Click the style button
    if i2i_model and i2i_model.get('style_btn'):
        btn = i2i_model['style_btn']
        page.mouse.click(btn['x'] + btn['w'] // 2, btn['y'] + btn['h'] // 2)
        page.wait_for_timeout(2500)
        ss(page, "P85_05_img2img_style_open")

        # Check for style list panel
        style_panel = page.evaluate("""() => {
            var sp = document.querySelector('.style-list-panel');
            if (!sp) return null;
            var r = sp.getBoundingClientRect();
            if (r.width === 0) return {found: true, visible: false};

            var cats = [];
            for (var el of sp.querySelectorAll('.category-item')) {
                var text = (el.innerText || '').trim();
                var sel = (el.className || '').includes('selected');
                if (text) cats.push({name: text, selected: sel});
            }

            var models = [];
            for (var el of sp.querySelectorAll('.item-name, .style-name')) {
                var text = (el.innerText || '').trim();
                if (text) models.push(text);
            }

            return {
                found: true, visible: true,
                bounds: {x: Math.round(r.x), y: Math.round(r.y),
                         w: Math.round(r.width), h: Math.round(r.height)},
                categories: cats,
                models: models.slice(0, 30),
            };
        }""")
        print(f"\n  Style panel: found={style_panel}", flush=True)
        if style_panel and style_panel.get('visible'):
            print(f"  Categories ({len(style_panel.get('categories', []))}):", flush=True)
            for c in style_panel.get('categories', []):
                sel = " [SELECTED]" if c['selected'] else ""
                print(f"    {c['name']}{sel}", flush=True)
            print(f"  Models ({len(style_panel.get('models', []))}):", flush=True)
            for m in style_panel.get('models', []):
                print(f"    {m}", flush=True)
    else:
        print("  No style button found in Img2Img panel", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: TXT2IMG COMPLETE MODEL LIST
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: TXT2IMG MODEL LIST", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Txt2Img panel
    open_panel(page, 40, 185, "Txt2Img")
    dismiss_popups(page)
    page.wait_for_timeout(1000)

    # Click style button to open model selector
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2500)
    ss(page, "P85_06_t2i_style_panel")

    # Get the "All styles" category
    page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (!sp) return false;
        for (var el of sp.querySelectorAll('.category-item')) {
            if ((el.innerText || '').trim() === 'All styles') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Now get ALL models by scrolling the grid
    all_models = page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (!sp) return [];
        var models = [];
        var seen = new Set();
        // Get the scrollable grid container
        var grid = sp.querySelector('.style-list, .style-grid, .grid-container, [class*="scroll"]');
        if (!grid) {
            // Try any scrollable child
            for (var child of sp.children) {
                var r = child.getBoundingClientRect();
                if (r.height > 200 && r.width > 400) {
                    grid = child; break;
                }
            }
        }
        // Get visible models
        for (var el of sp.querySelectorAll('.item-name, .style-name')) {
            var text = (el.innerText || '').trim();
            if (text && !seen.has(text)) {
                seen.add(text);
                var parent = el.closest('.style-item') || el.parentElement;
                var desc = parent ? parent.querySelector('.item-desc') : null;
                var descText = desc ? (desc.innerText || '').trim() : '';
                var labels = parent ? parent.querySelector('.item-labels') : null;
                var labelText = labels ? (labels.innerText || '').trim() : '';
                var hot = parent ? !!parent.querySelector('.item-hot') : false;
                var isNew = parent ? !!parent.querySelector('.item-new') : false;
                models.push({
                    name: text, desc: descText, labels: labelText,
                    hot: hot, new: isNew,
                });
            }
        }
        return models;
    }""")
    print(f"\n  Txt2Img models visible ({len(all_models)}):", flush=True)
    for m in all_models:
        flags = []
        if m.get('hot'): flags.append('HOT')
        if m.get('new'): flags.append('NEW')
        flag_str = f" [{', '.join(flags)}]" if flags else ''
        print(f"    {m['name']} — {m['desc']} | {m['labels']}{flag_str}", flush=True)

    # Scroll down to get more models
    page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (!sp) return;
        // Find scrollable area (usually right side of the panel)
        var scrollable = sp.querySelector('.ant-spin-container, [class*="list"], [class*="grid"]');
        if (scrollable) {
            scrollable.scrollTop = scrollable.scrollHeight;
        } else {
            // Try scrolling the panel itself
            for (var child of sp.querySelectorAll('*')) {
                if (child.scrollHeight > child.clientHeight + 50 && child.clientHeight > 200) {
                    child.scrollTop = child.scrollHeight;
                    break;
                }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Get models after scroll
    more_models = page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (!sp) return [];
        var models = [];
        var seen = new Set();
        for (var el of sp.querySelectorAll('.item-name, .style-name')) {
            var text = (el.innerText || '').trim();
            if (text && !seen.has(text)) {
                seen.add(text);
                var parent = el.closest('.style-item') || el.parentElement;
                var desc = parent ? parent.querySelector('.item-desc') : null;
                var descText = desc ? (desc.innerText || '').trim() : '';
                var labels = parent ? parent.querySelector('.item-labels') : null;
                var labelText = labels ? (labels.innerText || '').trim() : '';
                var hot = parent ? !!parent.querySelector('.item-hot') : false;
                var isNew = parent ? !!parent.querySelector('.item-new') : false;
                models.push({
                    name: text, desc: descText, labels: labelText,
                    hot: hot, new: isNew,
                });
            }
        }
        return models;
    }""")
    print(f"\n  After scroll ({len(more_models)} models):", flush=True)
    for m in more_models:
        flags = []
        if m.get('hot'): flags.append('HOT')
        if m.get('new'): flags.append('NEW')
        flag_str = f" [{', '.join(flags)}]" if flags else ''
        print(f"    {m['name']} — {m['desc']} | {m['labels']}{flag_str}", flush=True)

    # Get all categories for completeness
    cats = page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (!sp) return [];
        var cats = [];
        for (var el of sp.querySelectorAll('.category-item')) {
            var text = (el.innerText || '').trim();
            var sel = (el.className || '').includes('selected');
            cats.push({name: text, selected: sel});
        }
        return cats;
    }""")
    print(f"\n  All categories:", flush=True)
    for c in cats:
        sel = " [SELECTED]" if c['selected'] else ""
        print(f"    {c['name']}{sel}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: HEADER BAR COMPLETE MAPPING
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: HEADER BAR", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    header = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        // Header is typically the top bar (y < 50)
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y < 50 && r.y >= 0 && r.height > 10 && r.height < 50
                && r.width > 15 && r.width < 300 && r.x > 50) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1) {
                    var key = text + '|' + Math.round(r.x);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 30),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; }).slice(0, 30);
    }""")
    print(f"\n  Header bar elements ({len(header)}):", flush=True)
    for h in header:
        print(f"    x={h['x']} ({h['x']},{h['y']}) {h['w']}x{h['h']} <{h['tag']}> c='{h['classes'][:22]}' '{h['text']}'", flush=True)
    ss(page, "P85_07_header")

    # ============================================================
    #  PART 6: LAYERS PANEL (right side)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: LAYERS PANEL", flush=True)
    print("=" * 60, flush=True)

    # The layers panel is on the right side
    layers = page.evaluate("""() => {
        var lp = document.querySelector('.c-layers') ||
                 document.querySelector('.layers-panel') ||
                 document.querySelector('[class*="layer"]');
        if (!lp) return null;
        var r = lp.getBoundingClientRect();
        if (r.width < 10) return null;
        var items = [];
        for (var child of lp.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 40 && cr.width > 10 && cr.height > 5
                && text.indexOf('\\n') === -1) {
                items.push({
                    tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                    text: text,
                    classes: (child.className || '').toString().substring(0, 30),
                });
            }
        }
        return {
            bounds: {x: Math.round(r.x), y: Math.round(r.y),
                     w: Math.round(r.width), h: Math.round(r.height)},
            class: (lp.className || '').toString().substring(0, 50),
            items: items.slice(0, 20),
        };
    }""")
    if layers:
        print(f"  Layers panel: {layers['bounds']} class='{layers['class']}'", flush=True)
        print(f"  Items ({len(layers.get('items', []))}):", flush=True)
        for l in layers.get('items', []):
            print(f"    ({l['x']},{l['y']}) {l['w']}x{l['h']} <{l['tag']}> c='{l['classes'][:20]}' '{l['text']}'", flush=True)
    else:
        print("  Layers panel: NOT FOUND", flush=True)

    # Try alternative: look for layers in the right sidebar
    right_sidebar = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 1200 && r.width > 50 && r.height > 20 && r.height < 50
                && r.y > 50 && r.y < 900) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1) {
                    var key = text + '|' + Math.round(r.y);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 30),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"\n  Right sidebar elements ({len(right_sidebar)}):", flush=True)
    for rs in right_sidebar:
        print(f"    ({rs['x']},{rs['y']}) {rs['w']}x{rs['h']} <{rs['tag']}> c='{rs['classes'][:20]}' '{rs['text']}'", flush=True)

    # ============================================================
    #  PART 7: BOTTOM TOOLBAR (Undo/Redo/Zoom)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 7: BOTTOM TOOLBAR", flush=True)
    print("=" * 60, flush=True)

    bottom = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y > 820 && r.y < 900 && r.height > 10 && r.height < 50
                && r.width > 10 && r.width < 200 && r.x > 60 && r.x < 1400) {
                var text = (el.innerText || '').trim();
                var cls = (el.className || '').toString();
                if ((text.length > 0 && text.length < 30 && text.indexOf('\\n') === -1)
                    || cls.includes('ico-') || cls.includes('btn') || cls.includes('zoom')) {
                    var key = (text || cls.substring(0, 15)) + '|' + Math.round(r.x);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: cls.substring(0, 30),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; }).slice(0, 20);
    }""")
    print(f"\n  Bottom toolbar ({len(bottom)}):", flush=True)
    for b in bottom:
        print(f"    x={b['x']} ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> c='{b['classes'][:22]}' '{b['text']}'", flush=True)
    ss(page, "P85_08_bottom")

    print(f"\n\n===== PHASE 85 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
