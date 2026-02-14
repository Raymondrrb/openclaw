#!/usr/bin/env python3
"""Dzine Deep Exploration Part 4 — Targeted fixes.

Fixes from Part 3:
1. Switch to Key Frame mode before exploring video models
2. Fix SVG className bug (use getAttribute('class'))
3. Better model selector popup detection
4. Image Editor sub-tools via collapse-option clicks
5. Advanced settings exploration
"""

from __future__ import annotations
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19861203"
CDP_PORT = 18800
DL = Path.home() / "Downloads"
SX = 40

def connect():
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    return pw, browser, page

def close_dialogs(page):
    for _ in range(5):
        f = False
        for t in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                b = page.locator(f'button:has-text("{t}")')
                if b.count() > 0 and b.first.is_visible(timeout=300):
                    b.first.click(timeout=1000); f = True; page.wait_for_timeout(200)
            except: pass
        if not f: break

def ss(page, name):
    p = DL / f"{name}.png"; page.screenshot(path=str(p)); print(f"  [SS] {p}")

def ensure_canvas(page):
    if "canvas" not in (page.url or ""):
        page.goto(CANVAS_URL); page.wait_for_timeout(4000); close_dialogs(page)

def click_tool(page, y, wait=2000):
    other = 197 if y != 197 else 252
    page.mouse.click(SX, other); page.wait_for_timeout(800)
    page.mouse.click(SX, y); page.wait_for_timeout(wait); close_dialogs(page)

def panel_text(page):
    return page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        return p ? p.innerText : 'NO PANEL';
    }""")

# ======================================================================
# PART A: AI Video — Key Frame mode, model selector, camera
# ======================================================================
def explore_video(page):
    print("\n" + "="*70)
    print("PART A: AI Video — Key Frame + Model Selector + Camera")
    print("="*70)
    ensure_canvas(page)
    click_tool(page, 361, wait=2500)

    # Switch to Key Frame mode
    print("\n[A1] Switching to Key Frame mode...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var all = panel.querySelectorAll('div, button, span');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            if (t === 'Key Frame' && el.children.length <= 1) {
                el.click(); return 'clicked Key Frame';
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Verify Key Frame mode
    pt = panel_text(page)
    is_keyframe = 'Start Frame' in pt or 'Start and Last' in pt or 'Wan' in pt
    print(f"  Key Frame active: {is_keyframe}")
    print(f"  Panel snippet: {pt[:120]}")

    if not is_keyframe:
        # Click Key Frame tab directly by position
        print("  Retrying Key Frame click by position (72, 58)...")
        page.mouse.click(72, 58)
        page.wait_for_timeout(2000)
        pt = panel_text(page)
        print(f"  After retry: {pt[:120]}")

    ss(page, "p168_keyframe_mode")

    # Full panel text in Key Frame mode
    print("\n[A2] Key Frame panel text:")
    for line in pt.split('\n')[:25]:
        if line.strip(): print(f"    {line.strip()}")

    # Click model selector (the row with Wan 2.1 and an arrow)
    print("\n[A3] Opening model selector...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'no panel';
        var sel = panel.querySelector('.custom-selector-wrapper');
        if (sel) { sel.click(); return 'clicked'; }
    }""")
    page.wait_for_timeout(2500)
    ss(page, "p168_model_dropdown")

    # The model selector might open as a full overlay, not inside the panel
    # Search the ENTIRE document for model names
    print("\n[A4] Searching for model selector overlay...")
    models_data = page.evaluate("""() => {
        // Strategy: find ANY element that appeared with video model names
        var allText = document.body.innerText;
        var hasWan = allText.includes('Wan 2.5') || allText.includes('Wan 2.6');
        var hasSeedance = allText.includes('Seedance');
        var hasKling = allText.includes('Kling');

        if (!hasWan && !hasSeedance && !hasKling) {
            return {found: false, reason: 'no model names in body text'};
        }

        // Found model text! Now find the container
        var result = {found: true, models: []};
        var seen = new Set();

        // Get all elements and find ones with model-like text
        var all = document.querySelectorAll('div, span, button, li, a');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            // Look for model name patterns
            if (r.width > 80 && r.width < 400 && r.height > 15 && r.height < 60 && r.y > 0 && r.y < 900) {
                if ((t.match(/^(Wan|Seedance|Kling|Runway|Minimax|Sora|Google|Luma|Dzine|PixVerse|Vidu)/)) && !seen.has(t)) {
                    seen.add(t);
                    var cls = el.getAttribute('class') || '';
                    result.models.push({
                        name: t.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: cls.substring(0, 40)
                    });
                }
            }
        }

        // Also find the container panel
        var overlays = document.querySelectorAll('[style*="z-index"], [class*="overlay"], [class*="modal"], [class*="popup"], [class*="selector"]');
        for (var o of overlays) {
            var or2 = o.getBoundingClientRect();
            if (or2.width > 300 && or2.height > 300 && or2.y >= 0) {
                var cls2 = o.getAttribute('class') || '';
                result.overlay = {
                    cls: cls2.substring(0, 80),
                    w: Math.round(or2.width), h: Math.round(or2.height),
                    x: Math.round(or2.x), y: Math.round(or2.y)
                };
                break;
            }
        }

        return result;
    }""")
    print(f"  Found models: {models_data.get('found')}")
    if models_data.get('found'):
        print(f"  Overlay: {json.dumps(models_data.get('overlay', {}))}")
        print(f"  Models ({len(models_data.get('models', []))}):")
        for m in models_data.get('models', []):
            print(f"    [{m['x']},{m['y']}] {m['w']}x{m['h']} — {m['name']}")

        # Scroll the overlay to see all models
        if models_data.get('overlay'):
            ov = models_data['overlay']
            print(f"\n  Scrolling overlay...")
            page.evaluate(f"""() => {{
                var el = document.elementFromPoint({ov['x'] + ov['w']//2}, {ov['y'] + ov['h']//2});
                while (el) {{
                    if (el.scrollHeight > el.clientHeight + 50) {{
                        el.scrollTop = el.scrollHeight;
                        return 'scrolled: ' + (el.getAttribute('class') || '').substring(0, 40);
                    }}
                    el = el.parentElement;
                }}
                return 'nothing scrollable';
            }}""")
            page.wait_for_timeout(1000)

            more = page.evaluate("""() => {
                var seen = new Set();
                var result = [];
                var all = document.querySelectorAll('div, span');
                for (var el of all) {
                    var t = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (r.width > 80 && r.width < 400 && r.height > 15 && r.height < 60 && r.y > 0) {
                        if (t.match(/^(Wan|Seedance|Kling|Runway|Minimax|Sora|Google|Luma|Dzine|PixVerse|Vidu)/) && !seen.has(t)) {
                            seen.add(t);
                            result.push({name: t.substring(0, 60), y: Math.round(r.y)});
                        }
                    }
                }
                return result;
            }""")
            print(f"  After scroll ({len(more)} models):")
            for m in more:
                print(f"    [{m['y']}] {m['name']}")
            ss(page, "p168_model_dropdown_scrolled")
    else:
        # Model selector didn't open. Try clicking the model name text directly.
        print("  Model selector not open. Trying alternative clicks...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            // Find the Wan 2.1 row and click the arrow/chevron
            var all = panel.querySelectorAll('*');
            for (var el of all) {
                var t = (el.innerText || '').trim();
                if (t.includes('Wan 2.1') || t.includes('Wan 2.')) {
                    // Click the whole row
                    var row = el;
                    while (row && row !== panel) {
                        var r = row.getBoundingClientRect();
                        if (r.width > 150 && r.height > 30 && r.height < 60) {
                            row.click();
                            return 'clicked row at y=' + Math.round(r.y);
                        }
                        row = row.parentElement;
                    }
                }
            }
        }""")
        page.wait_for_timeout(2000)
        ss(page, "p168_model_alt_click")

    # Close model selector
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Explore Camera section
    print("\n[A5] Exploring Camera section...")
    # Scroll panel down
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (p) p.scrollTop = p.scrollHeight;
    }""")
    page.wait_for_timeout(500)
    ss(page, "p168_panel_scrolled")

    # Get text after scroll
    bottom_text = panel_text(page)
    print("  Bottom panel text:")
    for line in bottom_text.split('\n'):
        if line.strip(): print(f"    {line.strip()}")

    # Click Camera text
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return;
        var all = p.querySelectorAll('div, button, span');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            if (t === 'Camera') {
                el.click(); return 'clicked Camera';
            }
        }
    }""")
    page.wait_for_timeout(1500)
    ss(page, "p168_camera_section")

    # Map camera items - use getAttribute('class') to avoid SVG bug
    camera = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return {error: 'no panel'};
        var result = {items: [], images: 0};
        var all = p.querySelectorAll('*');
        for (var el of all) {
            var cls = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
            if (cls.includes('camera') || cls.includes('Camera')) {
                var r = el.getBoundingClientRect();
                var t = (el.innerText || '').trim();
                if (r.width > 10 && r.height > 10 && t.length < 100) {
                    result.items.push({
                        text: t.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: cls.substring(0, 40), tag: el.tagName
                    });
                }
            }
        }
        // Count images in lower half
        var imgs = p.querySelectorAll('img');
        for (var img of imgs) {
            var ir = img.getBoundingClientRect();
            if (ir.y > 400) result.images++;
        }
        return result;
    }""")
    print(f"\n  Camera elements: {json.dumps(camera, indent=2)}")


# ======================================================================
# PART B: Image Editor Sub-Tools
# ======================================================================
def explore_image_editor(page):
    print("\n" + "="*70)
    print("PART B: Image Editor Sub-Tools")
    print("="*70)
    ensure_canvas(page)
    click_tool(page, 698, wait=2500)

    pt = panel_text(page)
    has_ie = any(x in pt for x in ["Image Editor", "Local Edit", "Insert Object", "AI Eraser"])
    print(f"  Image Editor active: {has_ie}")

    if not has_ie:
        print(f"  Panel shows: {pt[:100]}")
        print("  Retrying...")
        # Try clicking Storyboard first (y=766) then Image Editor (y=698)
        page.mouse.click(SX, 766); page.wait_for_timeout(1000)
        page.mouse.click(SX, 698); page.wait_for_timeout(2500)
        close_dialogs(page)
        pt = panel_text(page)
        has_ie = any(x in pt for x in ["Image Editor", "Local Edit", "Insert Object"])
        print(f"  Retry result: {has_ie}, panel: {pt[:100]}")

    ss(page, "p169_image_editor")
    print("\n[B1] Full Image Editor panel:")
    for line in pt.split('\n')[:30]:
        if line.strip(): print(f"    {line.strip()}")

    # Map collapse-options
    sub_tools = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return [];
        var opts = p.querySelectorAll('.collapse-option');
        var result = [];
        for (var o of opts) {
            var r = o.getBoundingClientRect();
            result.push({
                text: (o.innerText || '').trim().substring(0, 50),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height)
            });
        }
        return result;
    }""")
    print(f"\n[B2] Collapse options ({len(sub_tools)}):")
    for st in sub_tools:
        print(f"    ({st['x']},{st['y']}) {st['w']}x{st['h']} — '{st['text']}'")

    # Scroll to see all
    page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); if (p) p.scrollTop = p.scrollHeight; }")
    page.wait_for_timeout(500)
    ss(page, "p169_image_editor_scrolled")

    more_tools = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return [];
        var opts = p.querySelectorAll('.collapse-option');
        var result = [];
        for (var o of opts) {
            var r = o.getBoundingClientRect();
            if (r.y > 0 && r.y < 900) {
                result.push({
                    text: (o.innerText || '').trim().substring(0, 50),
                    y: Math.round(r.y)
                });
            }
        }
        return result;
    }""")
    print(f"  After scroll ({len(more_tools)}):")
    for mt in more_tools:
        print(f"    [y={mt['y']}] '{mt['text']}'")

    # Click each sub-tool to map its panel
    for tool_text in ["Expand", "AI Eraser", "Hand Repair", "Face Swap", "Face Repair", "Expression Edit"]:
        print(f"\n[B3] Opening '{tool_text}'...")
        # Scroll to top first
        page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); if (p) p.scrollTop = 0; }")
        page.wait_for_timeout(300)

        clicked = page.evaluate(f"""() => {{
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return false;
            // Search visible and scrolled positions
            for (var scroll of [0, p.scrollHeight/2, p.scrollHeight]) {{
                p.scrollTop = scroll;
                var opts = p.querySelectorAll('.collapse-option');
                for (var o of opts) {{
                    var t = (o.innerText || '').trim();
                    if (t.includes('{tool_text}')) {{
                        o.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }}""")
        if not clicked:
            print(f"    Not found, skipping")
            continue

        page.wait_for_timeout(2000)
        close_dialogs(page)
        safe = tool_text.lower().replace(" ", "_")
        ss(page, f"p169_{safe}")

        # Get sub-panel text
        sub_pt = panel_text(page)
        print(f"    Panel:")
        for line in sub_pt.split('\n')[:15]:
            if line.strip(): print(f"      {line.strip()}")

        # Map key controls
        controls = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return {};
            var r = {};
            // Uploads
            var u = p.querySelectorAll('.pick-image, .upload-image-btn');
            r.uploads = u.length;
            // Textareas
            var ta = p.querySelectorAll('textarea, .custom-textarea');
            r.textareas = [];
            for (var t of ta) {
                var tr = t.getBoundingClientRect();
                if (tr.width > 50 && tr.y > 50) {
                    r.textareas.push({
                        placeholder: (t.placeholder || t.dataset.placeholder || '').substring(0, 60),
                        w: Math.round(tr.width), h: Math.round(tr.height),
                        maxlen: t.maxLength || 0
                    });
                }
            }
            // Generate
            var g = p.querySelector('.generative');
            if (g) r.generate = {text: (g.innerText||'').trim().substring(0,20), disabled: !!g.disabled};
            // Sliders
            r.sliders = p.querySelectorAll('.c-slider').length;
            return r;
        }""")
        print(f"    Controls: {json.dumps(controls)}")

        # Go back
        page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return;
            var back = p.querySelector('[class*="ico-back"], [class*="back"]:not([class*="background"])');
            if (back) back.click();
        }""")
        page.wait_for_timeout(1000)

        # Verify we're back in Image Editor main
        check = panel_text(page)
        if "Image Editor" not in check and "Local Edit" not in check:
            click_tool(page, 698, wait=2000)


# ======================================================================
# PART C: Txt2Img/Img2Img Advanced
# ======================================================================
def explore_advanced(page):
    print("\n" + "="*70)
    print("PART C: Txt2Img/Img2Img Advanced Settings")
    print("="*70)
    ensure_canvas(page)

    for name, y in [("Txt2Img", 197), ("Img2Img", 252)]:
        print(f"\n[C1] Opening {name} (y={y})...")
        click_tool(page, y, wait=2000)

        # Expand Advanced
        page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return;
            var all = p.querySelectorAll('button, div');
            for (var el of all) {
                if ((el.innerText || '').trim() === 'Advanced') { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(1500)

        # Scroll to see advanced section
        page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); if (p) p.scrollTop = p.scrollHeight; }")
        page.wait_for_timeout(500)
        ss(page, f"p170_{name.lower()}_advanced")

        # Map ALL panel content line by line
        pt = panel_text(page)
        print(f"\n  {name} full panel:")
        for line in pt.split('\n'):
            if line.strip(): print(f"    {line.strip()}")

        # Map all toggles WITH their labels
        toggles = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return [];
            var result = [];
            var switches = p.querySelectorAll('.c-switch');
            for (var sw of switches) {
                var r = sw.getBoundingClientRect();
                // Find label: walk up to parent row, get text excluding switch text
                var row = sw.parentElement;
                var label = '';
                if (row) {
                    var clone = row.cloneNode(true);
                    var swClone = clone.querySelector('.c-switch');
                    if (swClone) swClone.remove();
                    label = clone.innerText.trim();
                }
                result.push({
                    label: label.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    checked: (sw.getAttribute('class') || '').includes('isChecked')
                });
            }
            return result;
        }""")
        print(f"\n  Toggles ({len(toggles)}):")
        for t in toggles:
            state = "ON" if t['checked'] else "OFF"
            print(f"    [{t['x']},{t['y']}] {t['w']}x{t['h']} [{state}] '{t['label']}'")

        # Map all inputs
        inputs = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return [];
            var result = [];
            var inputs = p.querySelectorAll('input');
            for (var inp of inputs) {
                var r = inp.getBoundingClientRect();
                if (r.width > 30 && r.y > 50) {
                    result.push({
                        type: inp.type, value: inp.value || '',
                        placeholder: (inp.placeholder || '').substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width)
                    });
                }
            }
            return result;
        }""")
        print(f"\n  Inputs ({len(inputs)}):")
        for inp in inputs:
            print(f"    [{inp['x']},{inp['y']}] w={inp['w']} type={inp['type']} value='{inp['value']}' ph='{inp['placeholder']}'")

        # Map textareas (main prompt + negative prompt)
        tas = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return [];
            var result = [];
            var tas = p.querySelectorAll('textarea');
            for (var ta of tas) {
                var r = ta.getBoundingClientRect();
                if (r.width > 50) {
                    result.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        placeholder: (ta.placeholder || '').substring(0, 60),
                        maxlen: ta.maxLength || 0,
                        value: (ta.value || '').substring(0, 40)
                    });
                }
            }
            return result;
        }""")
        print(f"\n  Textareas ({len(tas)}):")
        for ta in tas:
            print(f"    [{ta['x']},{ta['y']}] {ta['w']}x{ta['h']} maxlen={ta['maxlen']} ph='{ta['placeholder']}'")


# ======================================================================
# MAIN
# ======================================================================
def main():
    print("="*70)
    print("DZINE DEEP EXPLORATION PART 4")
    print("="*70)
    pw, browser, page = connect()
    print(f"Connected. URL: {page.url}")
    try:
        explore_video(page)
        explore_image_editor(page)
        explore_advanced(page)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback; traceback.print_exc()
        ss(page, "p16x_error2")
    finally:
        print("\n" + "="*70 + "\nEXPLORATION PART 4 COMPLETE\n" + "="*70)

if __name__ == "__main__":
    main()
