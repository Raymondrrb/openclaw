#!/usr/bin/env python3
"""Dzine Deep Exploration Part 2 — Phases 158-163.

Follow-up exploration filling gaps from Part 1:
- Phase 158: Image Editor sub-tools (Product BG, Generative Expand, etc.)
- Phase 159: AI Video model selector + Camera controls
- Phase 160: Character tool
- Phase 161: Enhance & Upscale tool
- Phase 162: Instant Storyboard
- Phase 163: Txt2Img Advanced settings + all style categories

Saves screenshots to ~/Downloads/p15X_*.png and prints structured findings.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19861203"
CDP_PORT = 18800
DOWNLOADS = Path.home() / "Downloads"


def connect():
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    return pw, browser, page


def close_dialogs(page, rounds=5):
    for _ in range(rounds):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=300):
                    btn.first.click(timeout=1000)
                    found = True
                    page.wait_for_timeout(300)
            except Exception:
                pass
        if not found:
            break


def ss(page, name):
    path = DOWNLOADS / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  [SS] {path}")


def ensure_canvas(page):
    if "canvas" not in (page.url or ""):
        page.goto(CANVAS_URL)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        page.wait_for_timeout(1000)


def click_sidebar_item(page, name, wait=2000):
    """Click a sidebar tool by text label."""
    result = page.evaluate(f"""() => {{
        var items = document.querySelectorAll('.sidebar .item, nav .item, [class*="sidebar"] a, [class*="sidebar"] div');
        for (var item of items) {{
            var t = (item.innerText || '').trim();
            if (t.includes('{name}')) {{
                item.click();
                return t;
            }}
        }}
        return null;
    }}""")
    if result:
        print(f"  Clicked sidebar: {result}")
    else:
        print(f"  WARNING: sidebar item '{name}' not found")
    page.wait_for_timeout(wait)
    close_dialogs(page)
    return result


def get_panel_text(page):
    return page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.panels.show') ||
                    document.querySelector('[class*="panel"].show');
        if (!panel) return 'NO PANEL';
        return panel.innerText;
    }""")


# ======================================================================
# PHASE 158: Image Editor Sub-Tools
# ======================================================================

def phase_158_image_editor(page):
    print("\n" + "=" * 70)
    print("PHASE 158: Image Editor — All Sub-Tools")
    print("=" * 70)

    ensure_canvas(page)

    # Click Image Editor in sidebar
    print("\n[158a] Opening Image Editor...")
    click_sidebar_item(page, "Image Editor")

    # Map all sub-tool options in the Image Editor panel
    print("\n[158b] Mapping Image Editor sub-tools...")
    sub_tools = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel', body: document.body.innerText.substring(0, 300)};
        var options = panel.querySelectorAll('.collapse-option, .tool-item, .sub-tool, [class*="option"]');
        var result = [];
        for (var opt of options) {
            var t = (opt.innerText || '').trim();
            var r = opt.getBoundingClientRect();
            if (t && r.width > 40 && r.height > 10 && r.y > 0) {
                result.push({
                    text: t.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: opt.tagName, cls: (opt.className || '').substring(0, 50)
                });
            }
        }
        return result;
    }""")
    print(f"  Sub-tools ({len(sub_tools)} found):")
    for st in sub_tools:
        print(f"    ({st['x']},{st['y']}) {st['w']}x{st['h']} '{st['text']}'")

    ss(page, "p158_image_editor_overview")

    # Get full panel text
    panel_text = get_panel_text(page)
    print(f"\n[158c] Image Editor panel text:")
    for line in panel_text.split('\n')[:30]:
        if line.strip():
            print(f"    {line.strip()}")

    # Scroll the panel to see all options
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) panel.scrollTop = panel.scrollHeight;
    }""")
    page.wait_for_timeout(500)
    ss(page, "p158_image_editor_scrolled")

    panel_text_bottom = get_panel_text(page)
    for line in panel_text_bottom.split('\n'):
        l = line.strip()
        if l and l not in panel_text:
            print(f"    (scrolled) {l}")

    # Try clicking each sub-tool to map them
    for tool_name in ["Product Background", "Generative Expand", "Erase", "Sketch to Image"]:
        print(f"\n[158d] Trying to open '{tool_name}'...")
        # Scroll to top first
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) panel.scrollTop = 0;
        }""")
        page.wait_for_timeout(300)

        found = page.evaluate(f"""() => {{
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {{found: false, reason: 'no panel'}};
            // Search in all clickable elements
            var all = panel.querySelectorAll('*');
            for (var el of all) {{
                var t = (el.innerText || '').trim();
                if (t === '{tool_name}' || t.startsWith('{tool_name}')) {{
                    var r = el.getBoundingClientRect();
                    if (r.width > 20 && r.height > 10) {{
                        el.click();
                        return {{found: true, text: t.substring(0, 40), x: Math.round(r.x), y: Math.round(r.y)}};
                    }}
                }}
            }}
            // Try scrolling and searching
            panel.scrollTop = panel.scrollHeight / 2;
            for (var el of panel.querySelectorAll('*')) {{
                var t = (el.innerText || '').trim();
                if (t === '{tool_name}' || t.startsWith('{tool_name}')) {{
                    var r = el.getBoundingClientRect();
                    if (r.width > 20 && r.height > 10) {{
                        el.click();
                        return {{found: true, text: t.substring(0, 40), x: Math.round(r.x), y: Math.round(r.y), scrolled: true}};
                    }}
                }}
            }}
            return {{found: false, reason: 'not found in panel'}};
        }}""")
        print(f"    {json.dumps(found)}")

        if found.get("found"):
            page.wait_for_timeout(2000)
            close_dialogs(page)
            safe_name = tool_name.lower().replace(" ", "_")
            ss(page, f"p158_{safe_name}")

            # Get the sub-tool panel details
            details = get_panel_text(page)
            print(f"    Panel text for {tool_name}:")
            for line in details.split('\n')[:20]:
                if line.strip():
                    print(f"      {line.strip()}")

            # Go back to Image Editor overview
            page.evaluate("""() => {
                var back = document.querySelector('.c-gen-config.show .back') ||
                           document.querySelector('.c-gen-config.show .ico-back') ||
                           document.querySelector('.c-gen-config.show [class*="back"]');
                if (back) { back.click(); return true; }
                return false;
            }""")
            page.wait_for_timeout(1000)

    # Reset to Txt2Img
    click_sidebar_item(page, "Txt2Img")


# ======================================================================
# PHASE 159: AI Video Model Selector + Camera
# ======================================================================

def phase_159_video_models(page):
    print("\n" + "=" * 70)
    print("PHASE 159: AI Video — Model Selector + Camera Controls")
    print("=" * 70)

    ensure_canvas(page)

    print("\n[159a] Opening AI Video...")
    click_sidebar_item(page, "AI Video")

    # Click the model selector dropdown (Wan 2.1 row)
    print("\n[159b] Clicking model selector dropdown...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'no panel';
        // Find the model row with the arrow/chevron
        var items = panel.querySelectorAll('[class*="selector"], [class*="model-select"], .custom-selector-wrapper');
        for (var item of items) {
            var r = item.getBoundingClientRect();
            if (r.width > 100 && r.height > 20) {
                item.click();
                return 'clicked selector ' + (item.innerText || '').trim().substring(0, 30);
            }
        }
        // Fallback: click the model name text area
        var all = panel.querySelectorAll('*');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            if (t.includes('Wan 2.1') || t.includes('Seedance') || t.includes('Vidu')) {
                var r = el.getBoundingClientRect();
                if (r.width > 60 && r.height > 15 && r.height < 50) {
                    el.click();
                    return 'clicked model text: ' + t;
                }
            }
        }
        return 'no selector found';
    }""")
    page.wait_for_timeout(2000)

    # Map all video models in the dropdown
    print("\n[159c] Mapping all video models...")
    models = page.evaluate("""() => {
        // Look for the model selector popup/dropdown
        var selectors = document.querySelectorAll('.selector-panel, [class*="model-list"], [class*="dropdown"], .model-selector-panel, .popup-panel');
        for (var sel of selectors) {
            var r = sel.getBoundingClientRect();
            if (r.width > 100 && r.height > 100) {
                var items = sel.querySelectorAll('*');
                var models = [];
                var seen = new Set();
                for (var item of items) {
                    var t = (item.innerText || '').trim();
                    if (t.length > 3 && t.length < 50 && !seen.has(t) &&
                        (t.includes('Wan') || t.includes('Seedance') || t.includes('Vidu') ||
                         t.includes('Kling') || t.includes('Hailuo') || t.includes('Pika') ||
                         t.includes('Runway') || t.includes('Luma'))) {
                        seen.add(t);
                        var r2 = item.getBoundingClientRect();
                        models.push({
                            text: t, x: Math.round(r2.x), y: Math.round(r2.y),
                            w: Math.round(r2.width), tag: item.tagName,
                            cls: (item.className || '').substring(0, 40)
                        });
                    }
                }
                return {panel: sel.className.substring(0, 50), models: models, panel_text: sel.innerText.substring(0, 800)};
            }
        }
        // If no popup, check if the models are in the main panel
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            return {error: 'no dropdown popup', panel_text: panel.innerText.substring(0, 500)};
        }
        return {error: 'no panel at all'};
    }""")
    print(f"  Models: {json.dumps(models, indent=2)}")

    ss(page, "p159_video_model_dropdown")

    # Try clicking the model name directly to open dropdown
    if models.get("error"):
        print("\n[159c-retry] Trying direct click on model name...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var all = panel.querySelectorAll('div, span, button');
            for (var el of all) {
                var t = (el.innerText || '').trim();
                if (t === 'Wan 2.1' && el.children.length === 0) {
                    el.parentElement.click();
                    return 'clicked parent of Wan 2.1';
                }
            }
        }""")
        page.wait_for_timeout(2000)
        ss(page, "p159_video_model_retry")

        # Map popup that appeared
        popup_text = page.evaluate("""() => {
            var popups = document.querySelectorAll('.popup, [class*="popup"], [class*="dropdown"], [class*="selector-panel"]');
            for (var p of popups) {
                var r = p.getBoundingClientRect();
                if (r.width > 200 && r.height > 100) {
                    return {found: true, text: p.innerText.substring(0, 1000), cls: p.className.substring(0, 60)};
                }
            }
            return {found: false};
        }""")
        print(f"  Popup: {json.dumps(popup_text, indent=2)}")

    # Close dropdown and explore Camera controls
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    print("\n[159d] Exploring Camera controls...")
    # Click Camera to expand it
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var all = panel.querySelectorAll('*');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            if (t === 'Camera') {
                el.click();
                return true;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    camera = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        // Find camera section
        var result = {};
        var all = panel.querySelectorAll('[class*="camera"], [class*="Camera"]');
        result.camera_elements = [];
        for (var el of all) {
            var r = el.getBoundingClientRect();
            var t = (el.innerText || '').trim().substring(0, 60);
            if (r.width > 20 && r.height > 10) {
                result.camera_elements.push({
                    text: t, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (el.className || '').substring(0, 50)
                });
            }
        }
        // Also get all images/icons in the camera area
        var imgs = panel.querySelectorAll('.camera-motion img, [class*="camera"] img, [class*="camera"] svg');
        result.camera_icons = imgs.length;
        return result;
    }""")
    print(f"  Camera: {json.dumps(camera, indent=2)}")

    ss(page, "p159_camera_controls")

    # Scroll panel to see Camera section better
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) panel.scrollTop = panel.scrollHeight;
    }""")
    page.wait_for_timeout(500)
    ss(page, "p159_camera_scrolled")

    camera_text = get_panel_text(page)
    print(f"\n[159e] Full AI Video panel (scrolled):")
    for line in camera_text.split('\n'):
        if line.strip():
            print(f"    {line.strip()}")

    # Explore AnyFrame sub-tab
    print("\n[159f] Clicking AnyFrame tab...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var all = panel.querySelectorAll('*');
        for (var el of all) {
            if ((el.innerText || '').trim() === 'AnyFrame') {
                el.click();
                return true;
            }
        }
    }""")
    page.wait_for_timeout(1500)
    ss(page, "p159_anyframe")
    anyframe_text = get_panel_text(page)
    print(f"  AnyFrame panel:")
    for line in anyframe_text.split('\n')[:15]:
        if line.strip():
            print(f"    {line.strip()}")

    # Reset
    click_sidebar_item(page, "Txt2Img")


# ======================================================================
# PHASE 160: Character Tool
# ======================================================================

def phase_160_character(page):
    print("\n" + "=" * 70)
    print("PHASE 160: Character Tool")
    print("=" * 70)

    ensure_canvas(page)

    print("\n[160a] Opening Character tool...")
    click_sidebar_item(page, "Character")

    ss(page, "p160_character_panel")

    panel = get_panel_text(page)
    print(f"\n[160b] Character panel text:")
    for line in panel.split('\n')[:25]:
        if line.strip():
            print(f"    {line.strip()}")

    # Map all interactive elements
    details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Uploads
        var uploads = panel.querySelectorAll('.pick-image, .upload-image-btn');
        result.uploads = [];
        for (var u of uploads) {
            var r = u.getBoundingClientRect();
            result.uploads.push({
                text: (u.innerText || '').trim().substring(0, 50),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), cls: (u.className || '').substring(0, 40)
            });
        }
        // Prompt
        var ta = panel.querySelector('textarea, .custom-textarea');
        if (ta) {
            var r2 = ta.getBoundingClientRect();
            result.prompt = {x: Math.round(r2.x), y: Math.round(r2.y),
                            w: Math.round(r2.width), h: Math.round(r2.height),
                            placeholder: (ta.placeholder || '').substring(0, 60),
                            maxlen: ta.maxLength || 0};
        }
        // Toggles
        var switches = panel.querySelectorAll('.c-switch');
        result.toggles = [];
        for (var sw of switches) {
            var r3 = sw.getBoundingClientRect();
            var p = sw.parentElement;
            var label = '';
            if (p) {
                for (var c of p.childNodes) {
                    if (c !== sw && c.textContent) label += c.textContent.trim() + ' ';
                }
            }
            result.toggles.push({
                label: label.trim().substring(0, 40),
                x: Math.round(r3.x), y: Math.round(r3.y),
                checked: sw.className.includes('isChecked')
            });
        }
        // Generate button
        var gen = panel.querySelector('.generative');
        if (gen) {
            var r4 = gen.getBoundingClientRect();
            result.generate = {text: (gen.innerText || '').trim().substring(0, 30),
                              disabled: gen.disabled};
        }
        return result;
    }""")
    print(f"\n[160c] Character details: {json.dumps(details, indent=2)}")

    # Reset
    click_sidebar_item(page, "Txt2Img")


# ======================================================================
# PHASE 161: Enhance & Upscale
# ======================================================================

def phase_161_enhance(page):
    print("\n" + "=" * 70)
    print("PHASE 161: Enhance & Upscale")
    print("=" * 70)

    ensure_canvas(page)

    print("\n[161a] Opening Enhance & Upscale...")
    click_sidebar_item(page, "Enhance")

    ss(page, "p161_enhance_panel")

    panel = get_panel_text(page)
    print(f"\n[161b] Enhance panel text:")
    for line in panel.split('\n')[:25]:
        if line.strip():
            print(f"    {line.strip()}")

    details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Options/modes
        var btns = panel.querySelectorAll('button, .options');
        result.buttons = [];
        for (var b of btns) {
            var t = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (t && r.width > 30 && r.height > 15 && r.y > 30 && r.y < 800) {
                result.buttons.push({text: t.substring(0, 40), x: Math.round(r.x), y: Math.round(r.y),
                                    cls: (b.className || '').substring(0, 30)});
            }
        }
        // Sliders
        var sliders = panel.querySelectorAll('.c-slider, input[type="range"]');
        result.sliders = sliders.length;
        // Uploads
        var uploads = panel.querySelectorAll('.pick-image, .upload-image-btn');
        result.uploads = uploads.length;
        return result;
    }""")
    print(f"\n[161c] Enhance details: {json.dumps(details, indent=2)}")

    # Reset
    click_sidebar_item(page, "Txt2Img")


# ======================================================================
# PHASE 162: Instant Storyboard
# ======================================================================

def phase_162_storyboard(page):
    print("\n" + "=" * 70)
    print("PHASE 162: Instant Storyboard")
    print("=" * 70)

    ensure_canvas(page)

    print("\n[162a] Opening Instant Storyboard...")
    click_sidebar_item(page, "Storyboard")

    ss(page, "p162_storyboard_panel")

    panel = get_panel_text(page)
    print(f"\n[162b] Storyboard panel text:")
    for line in panel.split('\n')[:30]:
        if line.strip():
            print(f"    {line.strip()}")

    details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Prompt/textarea
        var ta = panel.querySelector('textarea, .custom-textarea');
        if (ta) {
            var r = ta.getBoundingClientRect();
            result.prompt = {x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            placeholder: (ta.placeholder || '').substring(0, 80),
                            maxlen: ta.maxLength || 0};
        }
        // All buttons
        var btns = panel.querySelectorAll('button');
        result.buttons = [];
        for (var b of btns) {
            var t = (b.innerText || '').trim();
            var r2 = b.getBoundingClientRect();
            if (t && r2.width > 30 && r2.y > 30 && r2.y < 800) {
                result.buttons.push({text: t.substring(0, 40), x: Math.round(r2.x), y: Math.round(r2.y)});
            }
        }
        return result;
    }""")
    print(f"\n[162c] Storyboard details: {json.dumps(details, indent=2)}")

    # Reset
    click_sidebar_item(page, "Txt2Img")


# ======================================================================
# PHASE 163: Txt2Img Advanced + Complete Style Catalog
# ======================================================================

def phase_163_advanced_styles(page):
    print("\n" + "=" * 70)
    print("PHASE 163: Txt2Img Advanced Settings + Complete Style Catalog")
    print("=" * 70)

    ensure_canvas(page)
    click_sidebar_item(page, "Txt2Img")

    # Map the full Txt2Img panel with toggle labels
    print("\n[163a] Mapping Txt2Img panel with labeled toggles...")
    full_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Get all labeled rows (label + toggle/slider/button)
        var rows = panel.querySelectorAll('.row, .form-row, [class*="row"], [class*="item"]');
        result.rows = [];
        for (var row of rows) {
            var t = (row.innerText || '').trim();
            var r = row.getBoundingClientRect();
            if (t && r.width > 100 && r.height > 10 && r.height < 80 && r.y > 50 && r.y < 800) {
                var hasSwitch = row.querySelector('.c-switch') !== null;
                var checked = row.querySelector('.c-switch.isChecked') !== null;
                result.rows.push({
                    text: t.substring(0, 50), y: Math.round(r.y),
                    hasToggle: hasSwitch, toggled: checked
                });
            }
        }
        return result;
    }""")
    print(f"  Panel rows: {json.dumps(full_panel, indent=2)}")

    # Click Advanced to expand it
    print("\n[163b] Opening Advanced section...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var all = panel.querySelectorAll('*');
        for (var el of all) {
            if ((el.innerText || '').trim() === 'Advanced') {
                el.click();
                return true;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    advanced = get_panel_text(page)
    print(f"\n[163c] Advanced settings expanded:")
    for line in advanced.split('\n'):
        if line.strip():
            print(f"    {line.strip()}")

    ss(page, "p163_txt2img_advanced")

    # Map Advanced section details
    adv_details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Seed input
        var inputs = panel.querySelectorAll('input[type="number"], input[type="text"]');
        result.inputs = [];
        for (var inp of inputs) {
            var r = inp.getBoundingClientRect();
            if (r.width > 30 && r.y > 50) {
                result.inputs.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), value: inp.value,
                    placeholder: inp.placeholder || '', type: inp.type
                });
            }
        }
        // Negative prompt
        var tas = panel.querySelectorAll('textarea');
        result.textareas = [];
        for (var ta of tas) {
            var r2 = ta.getBoundingClientRect();
            result.textareas.push({
                x: Math.round(r2.x), y: Math.round(r2.y),
                w: Math.round(r2.width), h: Math.round(r2.height),
                placeholder: (ta.placeholder || '').substring(0, 60),
                value: (ta.value || '').substring(0, 60)
            });
        }
        // Sliders
        var sliders = panel.querySelectorAll('.c-slider');
        result.sliders = [];
        for (var s of sliders) {
            var r3 = s.getBoundingClientRect();
            if (r3.y > 50) {
                // Get label from previous sibling or parent
                var label = '';
                var prev = s.previousElementSibling;
                if (prev) label = (prev.innerText || '').trim();
                result.sliders.push({
                    x: Math.round(r3.x), y: Math.round(r3.y),
                    w: Math.round(r3.width), label: label.substring(0, 30)
                });
            }
        }
        return result;
    }""")
    print(f"  Advanced details: {json.dumps(adv_details, indent=2)}")

    # Now explore the style catalog fully
    print("\n[163d] Opening style picker for full catalog...")
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    # Map ALL styles in the catalog
    print("\n[163e] Mapping complete style catalog...")
    styles = page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel, [class*="style-panel"], [class*="style-list"]');
        if (!panel) return {error: 'no style panel'};
        var result = {};

        // Categories in the sidebar
        var cats = panel.querySelectorAll('.menu-item, .category, nav a, nav div');
        result.categories = [];
        var seen = new Set();
        for (var cat of cats) {
            var t = (cat.innerText || '').trim();
            if (t && t.length < 30 && !seen.has(t)) {
                seen.add(t);
                result.categories.push(t);
            }
        }

        // All style cards/thumbnails visible
        var cards = panel.querySelectorAll('.style-item, [class*="style-card"], .grid-item');
        result.visible_styles = [];
        for (var card of cards) {
            var t2 = (card.innerText || '').trim();
            var r = card.getBoundingClientRect();
            if (t2 && r.width > 50 && r.height > 50) {
                result.visible_styles.push({
                    name: t2.substring(0, 40), x: Math.round(r.x), y: Math.round(r.y)
                });
            }
        }

        // Get all text from the panel to capture all style names
        result.all_text = panel.innerText.substring(0, 2000);

        return result;
    }""")
    print(f"  Style catalog categories: {json.dumps(styles.get('categories', []))}")
    print(f"  Visible styles: {len(styles.get('visible_styles', []))}")

    # Extract style names from the text
    all_text = styles.get('all_text', '')
    print(f"\n[163f] Full style panel text:")
    for line in all_text.split('\n'):
        if line.strip():
            print(f"    {line.strip()}")

    ss(page, "p163_style_catalog_full")

    # Scroll down to see more styles
    page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel, [class*="style-panel"]');
        if (panel) {
            var grid = panel.querySelector('.grid, [class*="grid"], [class*="list"]');
            if (grid) grid.scrollTop = grid.scrollHeight;
            else panel.scrollTop = panel.scrollHeight;
        }
    }""")
    page.wait_for_timeout(1000)
    ss(page, "p163_style_catalog_scrolled")

    more_text = page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel, [class*="style-panel"]');
        if (!panel) return '';
        return panel.innerText.substring(0, 2000);
    }""")
    # Print new lines not seen before
    for line in more_text.split('\n'):
        l = line.strip()
        if l and l not in all_text:
            print(f"    (more) {l}")

    # Click each category to see what styles it contains
    for cat_name in ["Realistic", "Portrait", "3D", "Anime", "Logo & Icon", "Scene"]:
        print(f"\n[163g] Clicking category: {cat_name}...")
        page.evaluate(f"""() => {{
            var panel = document.querySelector('.style-list-panel, [class*="style-panel"]');
            if (!panel) return;
            var all = panel.querySelectorAll('*');
            for (var el of all) {{
                var t = (el.innerText || '').trim();
                if (t === '{cat_name}') {{
                    el.click();
                    return true;
                }}
            }}
        }}""")
        page.wait_for_timeout(1000)

        cat_styles = page.evaluate("""() => {
            var panel = document.querySelector('.style-list-panel, [class*="style-panel"]');
            if (!panel) return '';
            // Get just the style names from the grid area
            var grid = panel.querySelector('[class*="grid"], [class*="content"]');
            if (grid) return grid.innerText.substring(0, 500);
            return panel.innerText.substring(0, 500);
        }""")
        styles_list = [l.strip() for l in cat_styles.split('\n') if l.strip() and len(l.strip()) > 2 and len(l.strip()) < 40]
        print(f"    Styles: {styles_list[:15]}")

    # Close style picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)


# ======================================================================
# PHASE 164: Lip Sync + Video Editor + Motion Control
# ======================================================================

def phase_164_extra_tools(page):
    print("\n" + "=" * 70)
    print("PHASE 164: Lip Sync + Video Editor + Motion Control")
    print("=" * 70)

    ensure_canvas(page)

    for tool_name in ["Lip Sync", "Video Editor", "Motion Control"]:
        print(f"\n[164] Opening {tool_name}...")
        click_sidebar_item(page, tool_name)

        safe = tool_name.lower().replace(" ", "_")
        ss(page, f"p164_{safe}")

        panel = get_panel_text(page)
        print(f"  {tool_name} panel:")
        for line in panel.split('\n')[:20]:
            if line.strip():
                print(f"    {line.strip()}")

    # Reset
    click_sidebar_item(page, "Txt2Img")


# ======================================================================
# MAIN
# ======================================================================

def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 2 — Phases 158-164")
    print("=" * 70)

    pw, browser, page = connect()
    print(f"Connected to Brave. Current URL: {page.url}")

    try:
        phase_158_image_editor(page)
        phase_159_video_models(page)
        phase_160_character(page)
        phase_161_enhance(page)
        phase_162_storyboard(page)
        phase_163_advanced_styles(page)
        phase_164_extra_tools(page)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        ss(page, "p16x_error")
    finally:
        print("\n" + "=" * 70)
        print("EXPLORATION PART 2 COMPLETE")
        print("=" * 70)
        print("Check ~/Downloads/p15*.png and p16*.png for screenshots")


if __name__ == "__main__":
    main()
