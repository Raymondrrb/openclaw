"""Phase 111: Explore Upload, Assets, Consistent Character, Enhance & Upscale.
P110 findings:
- Img2Img uses canvas content as input image
- Textarea: TEXTAREA.len-1800, click .prompt-textarea wrapper + keyboard.type()
- Generation progress: 0%→56%→82%→95%→99% (~80s total)
- Both Lip Sync videos completed: 7.68s, 720P
- 8 credits per Img2Img with Realistic Product

Goal: 1) Explore Upload — how to place images on canvas (for Img2Img pipeline)
      2) Explore Assets — pre-loaded asset library
      3) Map Consistent Character panel fully
      4) Map Enhance & Upscale panel fully
      5) Check canvas element management (layers, selection)
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


def close_blocking_panels(page):
    """Close any panel that blocks the sidebar."""
    page.evaluate("""() => {
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
        var panels = document.querySelector('.panels.show');
        if (panels) {
            var close = panels.querySelector('.ico-close');
            if (close) close.click();
        }
        var gen = document.querySelector('.c-gen-config.show');
        if (gen) {
            var close = gen.querySelector('.ico-close');
            if (close) close.click();
        }
    }""")
    page.wait_for_timeout(1000)


def open_tool_by_toggle(page, target_y):
    """Open a tool by panel toggle: click distant tool first, then target."""
    # Click a distant tool (Storyboard at 766) to ensure panels reset
    close_blocking_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    close_blocking_panels(page)
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
    #  STEP 1: Map sidebar icons precisely
    # ============================================================
    print("\n=== STEP 1: Sidebar icon map ===", flush=True)

    sidebar = page.evaluate("""() => {
        var groups = document.querySelectorAll('.tool-group');
        var items = [];
        for (var g of groups) {
            var r = g.getBoundingClientRect();
            var text = (g.innerText || '').trim();
            var icon = g.querySelector('svg, [class*="icon"], [class*="ico"]');
            var iconClass = icon ? (icon.className || '').toString().substring(0, 40) : '';
            items.push({
                text: text.substring(0, 20),
                class: (g.className || '').toString().substring(0, 60),
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
                iconClass: iconClass,
            });
        }
        return items;
    }""")

    print(f"  Sidebar tools ({len(sidebar)}):", flush=True)
    for s in sidebar:
        print(f"    '{s['text'][:15]}' at ({s['x']},{s['y']}) {s['w']}x{s['h']}", flush=True)

    # ============================================================
    #  STEP 2: Explore Upload
    # ============================================================
    print("\n=== STEP 2: Upload ===", flush=True)

    # Upload is the first sidebar icon
    close_blocking_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 45)  # Upload icon at top
    page.wait_for_timeout(2000)
    close_dialogs(page)

    upload_panel = page.evaluate("""() => {
        // Check for any new panel or dialog
        var panels = [];
        for (var el of document.querySelectorAll('.c-gen-config.show, .panels.show, [class*="upload"][class*="panel"], [class*="upload"][class*="dialog"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 50) {
                panels.push({
                    class: (el.className || '').toString().substring(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').substring(0, 200),
                });
            }
        }

        // Check for file input
        var fileInputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            fileInputs.push({
                accept: inp.accept || '',
                multiple: inp.multiple,
                class: (inp.className || '').toString().substring(0, 40),
            });
        }

        return {panels: panels, fileInputs: fileInputs};
    }""")

    print(f"  Upload panels: {len(upload_panel.get('panels', []))}", flush=True)
    for p in upload_panel.get('panels', []):
        print(f"    .{p['class'][:60]}", flush=True)
        print(f"      ({p['x']},{p['y']}) {p['w']}x{p['h']}", flush=True)
        print(f"      text: {p['text'][:100]}", flush=True)
    print(f"  File inputs: {json.dumps(upload_panel.get('fileInputs', []))}", flush=True)

    ss(page, "P111_01_upload")

    # ============================================================
    #  STEP 3: Explore Assets
    # ============================================================
    print("\n=== STEP 3: Assets ===", flush=True)

    close_blocking_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 80)  # Assets icon (second from top)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    assets_panel = page.evaluate("""() => {
        var panels = [];
        for (var el of document.querySelectorAll('.c-gen-config.show, .panels.show, [class*="asset"][class*="panel"], [class*="library"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 50) {
                panels.push({
                    class: (el.className || '').toString().substring(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').substring(0, 300),
                });
            }
        }
        return panels;
    }""")

    print(f"  Assets panels: {len(assets_panel)}", flush=True)
    for p in assets_panel:
        print(f"    .{p['class'][:60]}", flush=True)
        print(f"      ({p['x']},{p['y']}) {p['w']}x{p['h']}", flush=True)
        print(f"      text: {p['text'][:150]}", flush=True)

    ss(page, "P111_02_assets")

    # ============================================================
    #  STEP 4: Explore Consistent Character panel
    # ============================================================
    print("\n=== STEP 4: Consistent Character ===", flush=True)

    # Character is at sidebar position ~157 (between Img2Img and AI Video)
    open_tool_by_toggle(page, 157)

    cc_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show, .panels.show');
        if (!p) return {error: 'no panel'};

        var r = p.getBoundingClientRect();

        // Get all inputs
        var inputs = [];
        for (var el of p.querySelectorAll('textarea, input, [contenteditable="true"], [class*="textarea"], [class*="prompt"]')) {
            var ir = el.getBoundingClientRect();
            if (ir.width < 20) continue;
            inputs.push({
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                placeholder: el.getAttribute('placeholder') || '',
                x: Math.round(ir.x), y: Math.round(ir.y),
                w: Math.round(ir.width), h: Math.round(ir.height),
            });
        }

        // Get all buttons
        var buttons = [];
        for (var btn of p.querySelectorAll('button, [class*="btn"]')) {
            var br = btn.getBoundingClientRect();
            if (br.width < 20 || br.height < 10) continue;
            var text = (btn.innerText || '').trim();
            buttons.push({
                tag: btn.tagName,
                class: (btn.className || '').toString().substring(0, 60),
                text: text.substring(0, 40),
                disabled: btn.disabled,
                x: Math.round(br.x), y: Math.round(br.y),
                w: Math.round(br.width), h: Math.round(br.height),
            });
        }

        // Image upload areas
        var uploads = [];
        for (var el of p.querySelectorAll('[class*="upload"], [class*="pick"], [class*="drag"]')) {
            var ur = el.getBoundingClientRect();
            if (ur.width > 30 && ur.height > 30) {
                uploads.push({
                    class: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 60),
                    x: Math.round(ur.x), y: Math.round(ur.y),
                    w: Math.round(ur.width), h: Math.round(ur.height),
                });
            }
        }

        // Style/model selector
        var style = p.querySelector('.style-name, .style, [class*="model"]');
        var styleInfo = null;
        if (style) {
            var sr = style.getBoundingClientRect();
            styleInfo = {
                class: (style.className || '').toString().substring(0, 60),
                text: (style.innerText || '').trim().substring(0, 40),
                x: Math.round(sr.x), y: Math.round(sr.y),
            };
        }

        return {
            panelClass: (p.className || '').toString().substring(0, 80),
            title: (p.querySelector('h5') || {}).innerText || '',
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            fullText: (p.innerText || '').substring(0, 500),
            inputs: inputs,
            buttons: buttons.slice(0, 15),
            uploads: uploads.slice(0, 5),
            style: styleInfo,
        };
    }""")

    print(f"  Panel: .{cc_panel.get('panelClass', '')[:60]}", flush=True)
    print(f"  Title: {cc_panel.get('title')}", flush=True)
    print(f"  ({cc_panel.get('x')},{cc_panel.get('y')}) {cc_panel.get('w')}x{cc_panel.get('h')}", flush=True)
    print(f"  Style: {json.dumps(cc_panel.get('style'))}", flush=True)

    print(f"\n  Full text:\n{cc_panel.get('fullText', '')[:300]}", flush=True)

    print(f"\n  INPUTS ({len(cc_panel.get('inputs', []))}):", flush=True)
    for inp in cc_panel.get('inputs', []):
        print(f"    <{inp['tag']}> .{inp['class'][:50]} ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']}", flush=True)
        print(f"      placeholder: '{inp['placeholder'][:40]}'", flush=True)

    print(f"\n  BUTTONS ({len(cc_panel.get('buttons', []))}):", flush=True)
    for btn in cc_panel.get('buttons', []):
        print(f"    <{btn['tag']}> .{btn['class'][:50]} '{btn['text'][:30]}' ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']}", flush=True)

    print(f"\n  UPLOADS ({len(cc_panel.get('uploads', []))}):", flush=True)
    for u in cc_panel.get('uploads', []):
        print(f"    .{u['class'][:50]} '{u['text'][:40]}' ({u['x']},{u['y']}) {u['w']}x{u['h']}", flush=True)

    ss(page, "P111_03_consistent_character")

    # ============================================================
    #  STEP 5: Explore Enhance & Upscale panel
    # ============================================================
    print("\n=== STEP 5: Enhance & Upscale ===", flush=True)

    # Enhance & Upscale is near bottom of sidebar
    open_tool_by_toggle(page, 330)  # Try around y=330

    eu_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show, .panels.show');
        if (!p) return {error: 'no panel'};

        var title = (p.querySelector('h5') || {}).innerText || '';
        var r = p.getBoundingClientRect();

        // All text content
        var fullText = (p.innerText || '').substring(0, 600);

        // Buttons
        var buttons = [];
        for (var btn of p.querySelectorAll('button, [class*="btn"]')) {
            var br = btn.getBoundingClientRect();
            if (br.width < 20 || br.height < 10) continue;
            buttons.push({
                class: (btn.className || '').toString().substring(0, 60),
                text: (btn.innerText || '').trim().substring(0, 40),
                disabled: btn.disabled,
                x: Math.round(br.x), y: Math.round(br.y),
                w: Math.round(br.width),
            });
        }

        // Sliders
        var sliders = [];
        for (var sl of p.querySelectorAll('[class*="slider"], input[type="range"]')) {
            var sr = sl.getBoundingClientRect();
            if (sr.width > 50) {
                sliders.push({
                    class: (sl.className || '').toString().substring(0, 50),
                    x: Math.round(sr.x), y: Math.round(sr.y),
                    w: Math.round(sr.width),
                });
            }
        }

        // Image upload/preview areas
        var uploads = [];
        for (var el of p.querySelectorAll('[class*="upload"], [class*="pick"], [class*="preview"], [class*="image-input"]')) {
            var ur = el.getBoundingClientRect();
            if (ur.width > 30 && ur.height > 30) {
                uploads.push({
                    class: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 50),
                    x: Math.round(ur.x), y: Math.round(ur.y),
                    w: Math.round(ur.width), h: Math.round(ur.height),
                });
            }
        }

        return {
            panelClass: (p.className || '').toString().substring(0, 80),
            title: title,
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            fullText: fullText,
            buttons: buttons.slice(0, 15),
            sliders: sliders.slice(0, 5),
            uploads: uploads.slice(0, 5),
        };
    }""")

    print(f"  Panel: .{eu_panel.get('panelClass', '')[:60]}", flush=True)
    print(f"  Title: {eu_panel.get('title')}", flush=True)
    print(f"  ({eu_panel.get('x')},{eu_panel.get('y')}) {eu_panel.get('w')}x{eu_panel.get('h')}", flush=True)
    print(f"\n  Full text:\n{eu_panel.get('fullText', '')[:300]}", flush=True)

    print(f"\n  BUTTONS ({len(eu_panel.get('buttons', []))}):", flush=True)
    for btn in eu_panel.get('buttons', []):
        print(f"    .{btn['class'][:50]} '{btn['text'][:30]}' ({btn['x']},{btn['y']}) w={btn['w']}", flush=True)

    print(f"\n  SLIDERS ({len(eu_panel.get('sliders', []))}):", flush=True)
    for sl in eu_panel.get('sliders', []):
        print(f"    .{sl['class'][:50]} ({sl['x']},{sl['y']}) w={sl['w']}", flush=True)

    print(f"\n  UPLOADS ({len(eu_panel.get('uploads', []))}):", flush=True)
    for u in eu_panel.get('uploads', []):
        print(f"    .{u['class'][:50]} '{u['text'][:40]}' ({u['x']},{u['y']}) {u['w']}x{u['h']}", flush=True)

    ss(page, "P111_04_enhance_upscale")

    # ============================================================
    #  STEP 6: Explore canvas elements / layers
    # ============================================================
    print("\n=== STEP 6: Canvas layers ===", flush=True)

    # Click "Layers" tab in the right panel
    layers = page.evaluate("""() => {
        // Find Layers tab
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Layers' && r.x > 1000 && r.y < 50 && r.width > 30) {
                el.click();
                return {clicked: true, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return {clicked: false};
    }""")
    print(f"  Layers tab: {json.dumps(layers)}", flush=True)
    page.wait_for_timeout(1500)

    # Map layers content
    layers_content = page.evaluate("""() => {
        // Find the layers panel
        var layerItems = [];
        for (var el of document.querySelectorAll('[class*="layer-item"], [class*="layer-row"], [class*="layers"] [class*="item"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 50 || r.height < 20 || r.x < 800) continue;
            layerItems.push({
                class: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Get layers panel full content
        var layerPanel = null;
        for (var el of document.querySelectorAll('[class*="layers"], [class*="layer-panel"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 200 && r.height > 100 && r.x > 800) {
                layerPanel = {
                    class: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').substring(0, 300),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
                break;
            }
        }

        return {items: layerItems.slice(0, 10), panel: layerPanel};
    }""")

    if layers_content.get('panel'):
        lp = layers_content['panel']
        print(f"  Layers panel: .{lp['class'][:50]} ({lp['x']},{lp['y']}) {lp['w']}x{lp['h']}", flush=True)
        print(f"  Content: {lp['text'][:200]}", flush=True)

    print(f"  Layer items: {len(layers_content.get('items', []))}", flush=True)
    for li in layers_content.get('items', []):
        print(f"    .{li['class'][:40]} '{li['text'][:30]}' ({li['x']},{li['y']}) {li['w']}x{li['h']}", flush=True)

    ss(page, "P111_05_layers")

    # ============================================================
    #  STEP 7: Explore top toolbar (canvas operations)
    # ============================================================
    print("\n=== STEP 7: Top toolbar ===", flush=True)

    toolbar = page.evaluate("""() => {
        // Map the top toolbar buttons/icons
        var items = [];
        for (var el of document.querySelectorAll('[class*="tool-bar"] *, [class*="toolbar"] *')) {
            var r = el.getBoundingClientRect();
            if (r.y > 60 || r.width < 15 || r.height < 15 || r.x < 80) continue;
            var text = (el.innerText || '').trim();
            var title = el.title || el.getAttribute('aria-label') || '';
            var cls = (el.className || '').toString();
            if (text.length > 0 || title.length > 0) {
                items.push({
                    tag: el.tagName,
                    class: cls.substring(0, 50),
                    text: text.substring(0, 20),
                    title: title.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        // Deduplicate by position
        var unique = [];
        var seen = new Set();
        for (var item of items) {
            var key = `${Math.round(item.x/10)}-${Math.round(item.y/10)}`;
            if (!seen.has(key)) {
                seen.add(key);
                unique.push(item);
            }
        }
        return unique.slice(0, 20);
    }""")

    print(f"  Toolbar items ({len(toolbar)}):", flush=True)
    for t in toolbar:
        print(f"    '{t['text'][:15]}' title='{t['title'][:20]}' ({t['x']},{t['y']}) {t['w']}x{t['h']}", flush=True)

    # ============================================================
    #  STEP 8: Check the canvas element structure (Fabric.js?)
    # ============================================================
    print("\n=== STEP 8: Canvas structure ===", flush=True)

    canvas_info = page.evaluate("""() => {
        // Check for Fabric.js canvas
        var canvases = document.querySelectorAll('canvas');
        var canvasInfo = [];
        for (var c of canvases) {
            var r = c.getBoundingClientRect();
            if (r.width > 200 && r.height > 200) {
                canvasInfo.push({
                    id: c.id || '',
                    class: (c.className || '').toString().substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    canvasWidth: c.width, canvasHeight: c.height,
                });
            }
        }

        // Check for Fabric.js instance
        var hasFabric = typeof fabric !== 'undefined';
        var fabricCanvas = null;
        if (hasFabric) {
            // Try to find the fabric canvas instance
            try {
                var fCanvas = fabric.Canvas.__instances ? fabric.Canvas.__instances[0] : null;
                if (fCanvas) {
                    var objects = fCanvas.getObjects();
                    fabricCanvas = {
                        objectCount: objects.length,
                        objects: objects.map(function(o) {
                            return {
                                type: o.type,
                                left: Math.round(o.left || 0),
                                top: Math.round(o.top || 0),
                                width: Math.round(o.width || 0),
                                height: Math.round(o.height || 0),
                                src: o._element ? (o._element.src || '').substring(0, 100) : null,
                            };
                        }).slice(0, 10),
                    };
                }
            } catch(e) {}
        }

        // Check for any global canvas manager
        var hasCanvasManager = false;
        for (var key of ['canvasManager', 'editor', 'canvas', 'app']) {
            if (window[key]) hasCanvasManager = true;
        }

        return {
            canvases: canvasInfo,
            hasFabric: hasFabric,
            fabricCanvas: fabricCanvas,
            hasCanvasManager: hasCanvasManager,
        };
    }""")

    print(f"  Canvas elements: {len(canvas_info.get('canvases', []))}", flush=True)
    for c in canvas_info.get('canvases', []):
        print(f"    #{c['id']} .{c['class'][:30]} ({c['x']},{c['y']}) {c['w']}x{c['h']} canvas={c['canvasWidth']}x{c['canvasHeight']}", flush=True)
    print(f"  Has Fabric.js: {canvas_info.get('hasFabric')}", flush=True)
    print(f"  Has canvas manager: {canvas_info.get('hasCanvasManager')}", flush=True)
    if canvas_info.get('fabricCanvas'):
        fc = canvas_info['fabricCanvas']
        print(f"  Fabric objects: {fc['objectCount']}", flush=True)
        for obj in fc.get('objects', []):
            print(f"    {obj['type']} ({obj['left']},{obj['top']}) {obj['width']}x{obj['height']}", flush=True)
            if obj.get('src'):
                print(f"      src: {obj['src'][:80]}", flush=True)

    # ============================================================
    #  STEP 9: Look at the Img2Img result images
    # ============================================================
    print("\n=== STEP 9: Img2Img result details ===", flush=True)

    # Scroll results to top and check Img2Img results
    img2img_results = page.evaluate("""() => {
        var results = [];
        for (var el of document.querySelectorAll('.result-item')) {
            var text = (el.innerText || '').trim();
            if (!text.includes('Image-to-Image')) continue;

            var r = el.getBoundingClientRect();
            var imgs = [];
            for (var img of el.querySelectorAll('img')) {
                var ir = img.getBoundingClientRect();
                if (ir.width > 30 && ir.height > 30) {
                    imgs.push({
                        src: (img.src || '').substring(0, 120),
                        x: Math.round(ir.x), y: Math.round(ir.y),
                        w: Math.round(ir.width), h: Math.round(ir.height),
                        natural: img.naturalWidth + 'x' + img.naturalHeight,
                    });
                }
            }

            results.push({
                text: text.substring(0, 80),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                images: imgs,
            });
        }
        return results;
    }""")

    print(f"  Img2Img results: {len(img2img_results)}", flush=True)
    for i, r in enumerate(img2img_results):
        print(f"  [{i}] ({r['x']},{r['y']}) {r['w']}x{r['h']}", flush=True)
        print(f"      text: {r['text'][:60]}", flush=True)
        print(f"      images: {len(r.get('images', []))}", flush=True)
        for img in r.get('images', [])[:4]:
            print(f"        ({img['x']},{img['y']}) {img['w']}x{img['h']} natural={img['natural']}", flush=True)
            print(f"          src: {img['src'][:80]}", flush=True)

    ss(page, "P111_06_final")

    # Credit check
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,]+$/) && parseInt(text.replace(',', '')) > 1000 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\n  Credits: {credits}", flush=True)

    print(f"\n\n===== PHASE 111 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
