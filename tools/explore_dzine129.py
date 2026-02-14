"""Phase 129: Get product visible on canvas — layer reorder OR new project.

P128 showed: Upload via sidebar worked (2→4 layers) but product went BEHIND
the 2 undeletable blue foam layers. Describe Canvas sees foam, not product.

Strategy A: Hide foam layers via eye icon, expose product underneath
Strategy B: Navigate to Dzine workspace, create truly new blank project
Strategy C: Use Img2Img "Reference Image" upload (bypass canvas entirely)
"""

import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path.home() / "Downloads"

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(8):
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


def wait_for_new_images(page, before_count, max_wait=120, label=""):
    start = time.time()
    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)
        current = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
        new_count = current - before_count
        if new_count > 0:
            print(f"  [{label}] Done in {elapsed}s! {new_count} new image(s)", flush=True)
            return new_count
        if elapsed % 10 == 0:
            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.result-panel *, .material-v2-result-content *')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/^\\d{1,3}%$/)) return text;
                }
                return null;
            }""")
            p = f" progress={progress}" if progress else ""
            print(f"  [{label}] {elapsed}s...{p}", flush=True)
        page.wait_for_timeout(3000)
    print(f"  [{label}] TIMEOUT after {max_wait}s", flush=True)
    return 0


def find_product_image():
    for p in DOWNLOAD_DIR.glob("amazon_SL1500_*.jpg"):
        if p.stat().st_size > 10000:
            return str(p)
    for p in DOWNLOAD_DIR.glob("amazon_product_*.jpg"):
        if p.stat().st_size > 10000:
            return str(p)
    for p in DOWNLOAD_DIR.glob("amazon_*.jpg"):
        if p.stat().st_size > 10000:
            return str(p)
    for p in DOWNLOAD_DIR.glob("amazon_*.png"):
        if p.stat().st_size > 10000:
            return str(p)
    return None


def main():
    print("=" * 60, flush=True)
    print("PHASE 129: Layer visibility fix + new project + Img2Img ref", flush=True)
    print("=" * 60, flush=True)

    ref_path = find_product_image()
    if ref_path:
        print(f"\n  Product image: {ref_path} ({os.path.getsize(ref_path)/1024:.1f} KB)", flush=True)
    else:
        print("\n  ERROR: No product image found!", flush=True)
        sys.exit(1)

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # Close all dzine tabs
    for p in ctx.pages:
        if "dzine.ai" in (p.url or ""):
            try:
                p.close()
            except Exception:
                pass

    # ============================================================
    #  STRATEGY A: On existing canvas, toggle layer visibility
    # ============================================================
    print("\n=== STRATEGY A: Toggle layer visibility on existing canvas ===", flush=True)

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    wait_for_canvas(page)
    close_dialogs(page)

    # Open Layers tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Layers') { el.click(); return 'clicked'; }
        }
        return 'not found';
    }""")
    page.wait_for_timeout(1000)

    # Get detailed layer info including visibility toggles
    layer_detail = page.evaluate("""() => {
        var layers = [];
        var items = document.querySelectorAll('.layer-item');
        for (var i = 0; i < items.length; i++) {
            var el = items[i];
            var r = el.getBoundingClientRect();
            var nameEl = el.querySelector('[class*="layer-name"], [class*="name"]');
            var name = nameEl ? (nameEl.innerText || '').trim() : '';

            // Eye icon / visibility toggle
            var eyeOpen = el.querySelector('.ico-eye-open, [class*="eye-open"], .ico-eye');
            var eyeClose = el.querySelector('.ico-eye-close, [class*="eye-close"]');
            var hasEye = eyeOpen || eyeClose;
            var isVisible = !eyeClose;

            // Three-dot menu
            var menu = el.querySelector('[class*="more"], .ico-more, .ant-dropdown-trigger');

            // Thumbnail
            var thumb = el.querySelector('img, canvas, [class*="thumb"]');

            layers.push({
                index: i,
                name: name,
                visible: isVisible,
                y: Math.round(r.y),
                height: Math.round(r.height),
                hasEyeToggle: !!hasEye,
                hasMenu: !!menu,
                hasThumbnail: !!thumb,
                html: el.innerHTML.substring(0, 200)
            });
        }
        return layers;
    }""")
    print(f"  Found {len(layer_detail)} layers:", flush=True)
    for l in layer_detail:
        print(f"    [{l['index']}] '{l['name']}' visible={l['visible']} eye={l['hasEyeToggle']} menu={l['hasMenu']} y={l['y']}", flush=True)

    ss(page, "P129_01_layers_panel")

    # Try to hide the foam layers (they should be the first 2 — the oldest)
    # In most canvas apps, the BOTTOM of the layer stack renders first (background)
    # The foam is "Layer 1" and "Background" — try hiding them

    # First, let's look for eye icons more carefully with hover
    for i in range(len(layer_detail)):
        layer_y = layer_detail[i]['y'] + layer_detail[i]['height'] // 2

        # Hover over layer to reveal eye icon
        page.mouse.move(950, layer_y)
        page.wait_for_timeout(500)

        eye_info = page.evaluate(f"""(idx) => {{
            var items = document.querySelectorAll('.layer-item');
            if (idx >= items.length) return null;
            var el = items[idx];
            var eyes = el.querySelectorAll('[class*="eye"], [class*="visible"], .ico-eye-open, .ico-eye-close, .ico-eye');
            var results = [];
            for (var e of eyes) {{
                var r = e.getBoundingClientRect();
                results.push({{cls: e.className.toString().substring(0, 60), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), w: Math.round(r.width)}});
            }}
            // Also check for three-dot / menu
            var menus = el.querySelectorAll('[class*="more"], .ant-dropdown-trigger, [class*="menu"]');
            var menuInfo = [];
            for (var m of menus) {{
                var r = m.getBoundingClientRect();
                menuInfo.push({{cls: m.className.toString().substring(0, 60), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}});
            }}
            return {{eyes: results, menus: menuInfo}};
        }}""", i)
        print(f"    Layer {i} eye/menu: {json.dumps(eye_info)}", flush=True)

    ss(page, "P129_02_layer_hover")

    # Now try clicking the eye icons on the foam layers to hide them
    # Based on the layer info, foam layers might be index 0 and 1
    # Let's try toggling visibility by clicking eye area on right side of each layer
    hidden_count = 0
    for i in range(min(2, len(layer_detail))):  # Hide first 2 layers (foam)
        layer_y = layer_detail[i]['y'] + layer_detail[i]['height'] // 2

        # The eye icon is typically on the far right of the layer item
        # Try clicking at x=1048 (right edge of layers panel)
        eye_x = 1048
        print(f"  Clicking eye at ({eye_x}, {layer_y}) for layer {i}...", flush=True)
        page.mouse.click(eye_x, layer_y)
        page.wait_for_timeout(500)

        # Check if layer is now hidden
        vis = page.evaluate(f"""(idx) => {{
            var items = document.querySelectorAll('.layer-item');
            if (idx >= items.length) return null;
            var el = items[idx];
            var eyeClose = el.querySelector('.ico-eye-close, [class*="eye-close"]');
            return !eyeClose;
        }}""", i)
        print(f"    Layer {i} visible after click: {vis}", flush=True)
        if vis is False:
            hidden_count += 1

    if hidden_count > 0:
        print(f"  Hidden {hidden_count} foam layer(s)!", flush=True)
        ss(page, "P129_03_foam_hidden")

        # Now check what Describe Canvas sees
        open_sidebar_tool(page, 252)

        page.evaluate("""() => {
            var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
            if (ta) { ta.value = ''; ta.dispatchEvent(new Event('input', {bubbles: true})); }
        }""")
        page.wait_for_timeout(500)

        page.evaluate("""() => {
            var btn = document.querySelector('button.autoprompt');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(6000)

        desc = page.evaluate("""() => {
            var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
            return ta ? ta.value.substring(0, 500) : '';
        }""")
        print(f"  Describe Canvas (after hiding foam): {desc[:200]}", flush=True)

        if "foam" not in desc.lower() and "mat" not in desc.lower() and len(desc) > 10:
            print("  SUCCESS: Canvas now shows the product, not foam!", flush=True)
        else:
            print("  Still seeing foam or empty — Strategy A partial", flush=True)
    else:
        print("  Could not hide foam layers — eye icons not found or not working", flush=True)

    # ============================================================
    #  STRATEGY B: Navigate to workspace, create new project
    # ============================================================
    print("\n=== STRATEGY B: Create new project from workspace ===", flush=True)

    # Navigate to the Dzine home/workspace
    page.goto("https://www.dzine.ai/home", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    ss(page, "P129_04_home")

    # Map all clickable elements to find "New Project" or "Create"
    home_elements = page.evaluate("""() => {
        var results = [];
        for (var el of document.querySelectorAll('button, a, [role="button"], [class*="create"], [class*="new"], [class*="add"], [class*="project"]')) {
            var text = (el.innerText || '').trim().substring(0, 80);
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.y < 800) {
                results.push({
                    text: text.replace(/\\n/g, ' | ').substring(0, 60),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    tag: el.tagName,
                    cls: (el.className || '').toString().substring(0, 80)
                });
            }
        }
        return results;
    }""")
    print(f"  Found {len(home_elements)} elements:", flush=True)
    for el in home_elements[:30]:
        print(f"    {el['tag']}.{el['cls'][:40]} ({el['x']},{el['y']}) {el['w']}x{el['h']}: '{el['text'][:50]}'", flush=True)

    # Also look for "+" icons or "blank canvas" links
    plus_elements = page.evaluate("""() => {
        var results = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.width < 300 && (
                text === '+' ||
                text.toLowerCase().includes('blank') ||
                text.toLowerCase().includes('new project') ||
                text.toLowerCase().includes('create new') ||
                text.toLowerCase().includes('new design') ||
                text.toLowerCase().includes('start from scratch')
            )) {
                results.push({
                    text: text.substring(0, 40),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    cls: (el.className || '').toString().substring(0, 80)
                });
            }
        }
        return results;
    }""")
    print(f"\n  Create/New/Blank elements: {json.dumps(plus_elements[:10])}", flush=True)

    # Try to find and click "New" or "Create" or "+"
    new_proj_url = None
    create_clicked = page.evaluate("""() => {
        // Priority 1: explicit "New Project" or "Create New"
        for (var el of document.querySelectorAll('button, a, [role="button"]')) {
            var text = (el.innerText || '').trim().toLowerCase();
            if (text.includes('new project') || text.includes('create new') || text === 'new' || text === '+') {
                el.click();
                return text;
            }
        }
        // Priority 2: "blank canvas" or "start from scratch"
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim().toLowerCase();
            if (text.includes('blank canvas') || text.includes('start from scratch')) {
                el.click();
                return text;
            }
        }
        // Priority 3: any element with class containing "create" or "new-project"
        var btn = document.querySelector('[class*="create-btn"], [class*="new-project"], [class*="add-project"]');
        if (btn) { btn.click(); return 'class-match: ' + btn.className.toString().substring(0, 40); }
        return null;
    }""")
    print(f"\n  Clicked: {create_clicked}", flush=True)

    if create_clicked:
        page.wait_for_timeout(5000)
        close_dialogs(page)
        new_proj_url = page.url
        print(f"  URL after click: {new_proj_url}", flush=True)

        # If we got a template selection, look for "Blank" option
        if "/canvas" not in new_proj_url:
            print("  Not on canvas yet — checking for template selection...", flush=True)
            ss(page, "P129_05_template_selection")

            page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text === 'blank' || text === 'blank canvas' || text === 'empty') {
                        el.click();
                        return text;
                    }
                }
            }""")
            page.wait_for_timeout(5000)
            close_dialogs(page)
            new_proj_url = page.url
            print(f"  URL after blank selection: {new_proj_url}", flush=True)

    # If we're on a NEW canvas
    if new_proj_url and "/canvas" in new_proj_url and "id=19797967" not in new_proj_url:
        print(f"\n  NEW CANVAS: {new_proj_url}", flush=True)
        wait_for_canvas(page)
        close_dialogs(page)

        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        print(f"  Layers on new canvas: {layers}", flush=True)
        ss(page, "P129_06_new_canvas")

        # Upload product image
        print("\n  Uploading product to new canvas...", flush=True)
        uploaded = False

        # Method: sidebar upload
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(40, 81)
            fc = fc_info.value
            fc.set_files(ref_path)
            page.wait_for_timeout(5000)
            layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
            print(f"  Layers after upload: {layers}", flush=True)
            if layers > 0:
                uploaded = True
        except Exception as e:
            print(f"  Sidebar upload failed: {e}", flush=True)

        if not uploaded:
            # Clipboard paste
            with open(ref_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('ascii')

            paste_ok = page.evaluate("""(jpegB64) => {
                return new Promise(async (resolve) => {
                    try {
                        var img = new Image();
                        img.onload = async function() {
                            var c = document.createElement('canvas');
                            c.width = img.width; c.height = img.height;
                            var ctx = c.getContext('2d');
                            ctx.drawImage(img, 0, 0);
                            c.toBlob(async function(pngBlob) {
                                try {
                                    await navigator.clipboard.write([new ClipboardItem({'image/png': pngBlob})]);
                                    resolve({ok: true, w: img.width, h: img.height});
                                } catch(e) { resolve({error: e.message}); }
                            }, 'image/png');
                        };
                        img.src = 'data:image/jpeg;base64,' + jpegB64;
                    } catch(e) { resolve({error: e.message}); }
                });
            }""", img_b64)
            if paste_ok.get('ok'):
                page.mouse.click(700, 450)
                page.wait_for_timeout(500)
                page.keyboard.press("Meta+v")
                page.wait_for_timeout(4000)
                layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
                if layers > 0:
                    uploaded = True

        if uploaded:
            print("  Product uploaded to new canvas!", flush=True)
            ss(page, "P129_07_product_on_new_canvas")
        else:
            print("  FAILED to upload to new canvas", flush=True)
    else:
        print(f"  Could not create new project (url={new_proj_url})", flush=True)
        print("  Falling back to Strategy C...", flush=True)

    # ============================================================
    #  STRATEGY C: Img2Img reference image upload (bypass canvas)
    # ============================================================
    print("\n=== STRATEGY C: Img2Img Reference Image upload ===", flush=True)

    # Go back to existing canvas if needed
    if "/canvas" not in page.url:
        page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
        wait_for_canvas(page)
        close_dialogs(page)

    # Open Img2Img panel
    open_sidebar_tool(page, 252)
    page.wait_for_timeout(1000)

    # Map the Img2Img panel completely
    img2img_panel = page.evaluate("""() => {
        var panel = document.querySelector('.img2img-config-panel, .c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        var results = {};

        // All clickable elements in the panel
        var clickables = [];
        for (var el of panel.querySelectorAll('button, [role="button"], .c-switch, [class*="upload"], [class*="pick"], [class*="reference"]')) {
            var text = (el.innerText || '').trim().substring(0, 40);
            var r = el.getBoundingClientRect();
            if (r.width > 0) {
                clickables.push({
                    text: text,
                    cls: el.className.toString().substring(0, 80),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
        }
        results.clickables = clickables;

        // All file inputs
        var fileInputs = [];
        for (var inp of panel.querySelectorAll('input[type="file"]')) {
            var r = inp.getBoundingClientRect();
            fileInputs.push({
                accept: inp.accept,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                visible: r.width > 0
            });
        }
        results.fileInputs = fileInputs;

        // Any reference image area
        var refs = [];
        for (var el of panel.querySelectorAll('[class*="ref"], [class*="upload"], [class*="pick-image"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim().substring(0, 40);
            refs.push({
                cls: el.className.toString().substring(0, 80),
                text: text,
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width)
            });
        }
        results.refs = refs;

        // "Advanced" section — may contain reference upload
        var adv = panel.querySelector('[class*="advanced"], .advanced-section');
        if (adv) {
            results.advancedHTML = adv.innerHTML.substring(0, 300);
        }

        return results;
    }""")
    print(f"  Img2Img panel elements:", flush=True)
    if 'clickables' in img2img_panel:
        for c in img2img_panel['clickables']:
            print(f"    [{c['cls'][:30]}] ({c['x']},{c['y']}) {c['w']}x{c['h']}: '{c['text'][:30]}'", flush=True)
    if 'fileInputs' in img2img_panel:
        print(f"  File inputs: {json.dumps(img2img_panel['fileInputs'])}", flush=True)
    if 'refs' in img2img_panel:
        print(f"  Reference areas: {json.dumps(img2img_panel['refs'])}", flush=True)

    ss(page, "P129_08_img2img_panel")

    # Click "Advanced" to expand it
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show *')) {
            var text = (el.innerText || '').trim();
            if (text === 'Advanced' || text === 'Advanced >' || text === 'Advanced Settings') {
                el.click();
                return text;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    # Check for reference upload in Advanced
    adv_content = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var all = [];
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text && r.width > 0 && r.y > 500) {
                all.push({
                    text: text.substring(0, 40),
                    cls: (el.className || '').toString().substring(0, 60),
                    y: Math.round(r.y)
                });
            }
        }
        return all;
    }""")
    if adv_content:
        print(f"  Advanced section elements (below y=500):", flush=True)
        seen = set()
        for el in adv_content[:20]:
            key = el['text'][:30]
            if key not in seen:
                print(f"    y={el['y']} [{el['cls'][:30]}]: {el['text']}", flush=True)
                seen.add(key)

    ss(page, "P129_09_advanced_section")

    # ============================================================
    #  STRATEGY D: Try Txt2Img with reference image
    # ============================================================
    print("\n=== STRATEGY D: Txt2Img with reference image ===", flush=True)

    open_sidebar_tool(page, 197)  # Txt2Img
    page.wait_for_timeout(1500)

    # Map the Txt2Img panel for reference upload areas
    txt2img_refs = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var results = [];
        for (var el of panel.querySelectorAll('[class*="ref"], [class*="upload"], [class*="pick-image"], [class*="image-reference"]')) {
            var r = el.getBoundingClientRect();
            results.push({
                cls: el.className.toString().substring(0, 80),
                text: (el.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width),
                h: Math.round(r.height)
            });
        }
        // Check for "Image Reference" or similar labels
        var labels = [];
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim().toLowerCase();
            if (text.includes('reference') || text.includes('upload image') || text.includes('add image')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0) {
                    labels.push({text: text.substring(0, 50), y: Math.round(r.y), cls: (el.className||'').toString().substring(0, 40)});
                }
            }
        }
        return {refs: results, labels: labels};
    }""")
    print(f"  Txt2Img reference areas: {json.dumps(txt2img_refs)}", flush=True)

    # Click Advanced in Txt2Img
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show *')) {
            var text = (el.innerText || '').trim();
            if (text === 'Advanced' || text === 'Advanced >' || text === 'Advanced Settings') {
                el.click();
                return text;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    ss(page, "P129_10_txt2img_advanced")

    # Look for the "Image Reference" feature  that might allow uploading a product photo
    ref_upload = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        // Scroll down in the panel to reveal more options
        panel.scrollTop = panel.scrollHeight;

        var all = [];
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && (
                text.toLowerCase().includes('reference') ||
                text.toLowerCase().includes('upload') ||
                el.className.toString().includes('ref') ||
                el.className.toString().includes('upload') ||
                el.className.toString().includes('pick-image')
            )) {
                all.push({
                    text: text.substring(0, 50),
                    cls: (el.className || '').toString().substring(0, 80),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    tag: el.tagName
                });
            }
        }
        return all;
    }""")
    print(f"  Reference upload elements: {json.dumps(ref_upload[:10] if ref_upload else [])}", flush=True)

    # Try to find and use any reference image upload area
    if ref_upload:
        for ref in ref_upload:
            if ref['w'] > 10 and ref['h'] > 10:
                print(f"  Trying ref upload at ({ref['x']},{ref['y']}) '{ref['text'][:30]}'...", flush=True)
                try:
                    with page.expect_file_chooser(timeout=3000) as fc_info:
                        page.mouse.click(ref['x'], ref['y'])
                    fc = fc_info.value
                    fc.set_files(ref_path)
                    print(f"  Reference image uploaded!", flush=True)
                    page.wait_for_timeout(3000)
                    ss(page, "P129_11_ref_uploaded")

                    # Now generate with the reference
                    page.evaluate("""() => {
                        var ta = document.querySelector('.c-gen-config.show textarea, TEXTAREA.len-1800');
                        if (ta) {
                            ta.value = 'Professional product photography. The exact product shown in the reference image on a clean white studio backdrop with soft professional lighting. Preserve every detail of the product design.';
                            ta.dispatchEvent(new Event('input', {bubbles: true}));
                        }
                    }""")
                    page.wait_for_timeout(500)

                    # Select Realistic Product style
                    page.evaluate("""() => {
                        var styleName = document.querySelector('.style-name');
                        if (styleName) styleName.click();
                    }""")
                    page.wait_for_timeout(2000)
                    page.evaluate("""() => {
                        var input = document.querySelector('.style-list-panel input[type="text"]');
                        if (input) { input.value = 'Realistic Product'; input.dispatchEvent(new Event('input', {bubbles: true})); }
                    }""")
                    page.wait_for_timeout(1500)
                    page.evaluate("""() => {
                        for (var item of document.querySelectorAll('[class*="style-item"]')) {
                            if ((item.innerText || '').trim() === 'Realistic Product') { item.click(); return; }
                        }
                    }""")
                    page.wait_for_timeout(1000)

                    # Generate
                    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
                    gen = page.evaluate("""() => {
                        var btn = document.querySelector('button.generative.ready');
                        if (btn && !btn.disabled) { btn.click(); return {clicked: true}; }
                        return {error: 'not ready'};
                    }""")
                    print(f"  Generate: {json.dumps(gen)}", flush=True)

                    if gen.get('clicked'):
                        page.wait_for_timeout(2000)
                        new_count = wait_for_new_images(page, before_count, max_wait=90, label="RefImg")

                        if new_count > 0:
                            urls = page.evaluate("""(count) => {
                                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
                                var urls = [];
                                for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) urls.push(imgs[i].src);
                                return urls;
                            }""", new_count)
                            ts = int(time.time())
                            for j, url in enumerate(urls):
                                path = DOWNLOAD_DIR / f"dzine_ref_{ts}_{j}.webp"
                                try:
                                    urllib.request.urlretrieve(url, str(path))
                                    print(f"  Downloaded: {path.name} ({path.stat().st_size/1024:.1f} KB)", flush=True)
                                except Exception as e:
                                    print(f"  Download failed: {e}", flush=True)

                            page.evaluate("""() => {
                                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
                                if (imgs.length > 0) imgs[imgs.length - 1].click();
                            }""")
                            page.wait_for_timeout(2000)
                            ss(page, "P129_12_ref_result")
                            page.keyboard.press("Escape")

                    break  # Only try first working upload
                except Exception as e:
                    print(f"  File chooser failed: {e}", flush=True)
                    continue

    # Summary
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

    ss(page, "P129_13_final")

    print(f"\n  Credits: {credits}", flush=True)
    print(f"  Canvas URL: {page.url}", flush=True)

    print(f"\n\n===== PHASE 129 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
