#!/usr/bin/env python3
"""Dzine Deep Exploration Part 3 — Tasks 34, 35, 37.

Targeted exploration using exact sidebar Y coordinates from UI map:
- Task 34: AI Video model selector + Camera controls
- Task 35: Image Editor sub-tools (Product BG, Expand, Eraser, Hand Repair)
- Task 37: Txt2Img/Img2Img Advanced settings

Uses sidebar Y positions confirmed in UI map:
  Txt2Img=197, Img2Img=252, Character=306, AI Video=361,
  Lip Sync=425, Video Editor=490, Motion Control=551,
  Enhance=628, Image Editor=698, Storyboard=766
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
SX = 40  # Sidebar center X


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
        print(f"  Navigating to canvas (was: {page.url})...")
        page.goto(CANVAS_URL)
        page.wait_for_timeout(4000)
        close_dialogs(page)
        page.wait_for_timeout(1000)


def click_tool(page, y, wait=2000):
    """Click sidebar tool at exact Y coordinate, with toggle-away trick."""
    # First click a different tool to force panel switch
    other_y = 197 if y != 197 else 252
    page.mouse.click(SX, other_y)
    page.wait_for_timeout(800)
    # Now click target
    page.mouse.click(SX, y)
    page.wait_for_timeout(wait)
    close_dialogs(page)


def get_panel_text(page):
    return page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.panels.show');
        if (!panel) return 'NO PANEL';
        return panel.innerText;
    }""")


def click_in_panel(page, text, wait=2000):
    """Click element containing exact text inside the active panel."""
    result = page.evaluate(f"""() => {{
        var panel = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.panels.show');
        if (!panel) return {{found: false, reason: 'no panel'}};
        var all = panel.querySelectorAll('*');
        for (var el of all) {{
            if (el.children.length === 0 || el.children.length === 1) {{
                var t = (el.innerText || '').trim();
                if (t === '{text}') {{
                    var r = el.getBoundingClientRect();
                    if (r.width > 10 && r.height > 5 && r.y > 0) {{
                        el.click();
                        return {{found: true, text: t, x: Math.round(r.x), y: Math.round(r.y)}};
                    }}
                }}
            }}
        }}
        return {{found: false, reason: 'text not found'}};
    }}""")
    if result.get("found"):
        page.wait_for_timeout(wait)
        close_dialogs(page)
    return result


# ======================================================================
# TASK 34: AI Video Model Selector + Camera
# ======================================================================

def task_34_video_models_camera(page):
    print("\n" + "=" * 70)
    print("TASK 34: AI Video — Model Selector + Camera Controls")
    print("=" * 70)

    ensure_canvas(page)

    # Open AI Video (y=361)
    print("\n[34a] Opening AI Video panel...")
    click_tool(page, 361)

    # Verify we're in AI Video
    panel = get_panel_text(page)
    print(f"  Panel starts with: {panel[:80]}")
    if "AI Video" not in panel:
        print("  WARNING: Not in AI Video panel. Retrying with fresh navigation...")
        ensure_canvas(page)
        click_tool(page, 361, wait=3000)
        panel = get_panel_text(page)
        print(f"  Retry panel: {panel[:80]}")

    ss(page, "p165_ai_video_before_model")

    # Click the model selector — it's the row showing "Wan 2.1" with an arrow
    print("\n[34b] Opening video model selector...")
    # The model row has class custom-selector-wrapper
    opened = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'no panel';
        // Method 1: Find custom-selector-wrapper
        var wrapper = panel.querySelector('.custom-selector-wrapper');
        if (wrapper) {
            wrapper.click();
            return 'clicked custom-selector-wrapper: ' + (wrapper.innerText || '').trim().substring(0, 30);
        }
        // Method 2: Find the model name text and click parent row
        var all = panel.querySelectorAll('div, button, span');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            if ((t === 'Wan 2.1' || t === 'Seedance' || t.includes('Wan 2.')) && el.children.length <= 2) {
                var p = el.closest('[class*="selector"]') || el.parentElement;
                p.click();
                return 'clicked parent of: ' + t;
            }
        }
        return 'no model selector found';
    }""")
    print(f"  {opened}")
    page.wait_for_timeout(2000)

    ss(page, "p165_model_selector_opened")

    # Map what appeared
    print("\n[34c] Mapping model selector popup...")
    popup = page.evaluate("""() => {
        // Look for popup/overlay/dropdown that appeared
        var candidates = document.querySelectorAll('[class*="selector"], [class*="popup"], [class*="dropdown"], [class*="modal"], [class*="overlay"]');
        for (var c of candidates) {
            var r = c.getBoundingClientRect();
            if (r.width > 200 && r.height > 200 && r.y > 0) {
                // Found the popup — get all model names
                var text = c.innerText;
                var models = [];
                var lines = text.split('\\n');
                for (var line of lines) {
                    var l = line.trim();
                    if (l && l.length > 2 && l.length < 60) {
                        models.push(l);
                    }
                }
                return {
                    found: true,
                    cls: c.className.substring(0, 80),
                    width: Math.round(r.width),
                    height: Math.round(r.height),
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    models: models.slice(0, 60),
                    full_text: text.substring(0, 2000)
                };
            }
        }
        // Fallback: check if something with lots of model names appeared anywhere
        var body = document.body.innerText;
        var hasModels = body.includes('Seedance') || body.includes('Kling') || body.includes('Runway');
        return {found: false, hasModelText: hasModels, bodySnippet: body.substring(0, 300)};
    }""")
    print(f"  Popup found: {popup.get('found')}")
    if popup.get("found"):
        print(f"  Popup size: {popup['width']}x{popup['height']} at ({popup['x']},{popup['y']})")
        print(f"  Class: {popup['cls']}")
        print(f"  Models ({len(popup['models'])} lines):")
        for m in popup['models']:
            print(f"    {m}")
    else:
        print(f"  No popup: {json.dumps(popup, indent=2)}")

    # Scroll the popup to find all models
    if popup.get("found"):
        print("\n[34d] Scrolling model popup to see all...")
        page.evaluate("""() => {
            var candidates = document.querySelectorAll('[class*="selector"], [class*="popup"]');
            for (var c of candidates) {
                var r = c.getBoundingClientRect();
                if (r.width > 200 && r.height > 200) {
                    // Find scrollable body
                    var body = c.querySelector('[class*="body"], [class*="content"], [class*="scroll"]');
                    if (body) { body.scrollTop = body.scrollHeight; return 'scrolled body'; }
                    c.scrollTop = c.scrollHeight;
                    return 'scrolled panel';
                }
            }
            return 'nothing to scroll';
        }""")
        page.wait_for_timeout(1000)

        more_models = page.evaluate("""() => {
            var candidates = document.querySelectorAll('[class*="selector"], [class*="popup"]');
            for (var c of candidates) {
                var r = c.getBoundingClientRect();
                if (r.width > 200 && r.height > 200) {
                    return c.innerText.substring(0, 2000);
                }
            }
            return '';
        }""")
        # Print new lines
        seen = set(popup.get('full_text', '').split('\n'))
        for line in more_models.split('\n'):
            l = line.strip()
            if l and l not in seen and len(l) > 2:
                print(f"    (more) {l}")

        ss(page, "p165_model_selector_scrolled")

    # Close model selector
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Explore Camera controls
    print("\n[34e] Exploring Camera controls...")
    # Scroll panel down to Camera section
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) panel.scrollTop = panel.scrollHeight;
    }""")
    page.wait_for_timeout(500)

    # Click Camera to expand it
    camera_clicked = click_in_panel(page, "Camera", wait=1500)
    print(f"  Camera click: {json.dumps(camera_clicked)}")

    ss(page, "p165_camera_expanded")

    # Map camera motion options
    camera = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        // Get all text near bottom of panel (camera section)
        var result = {};
        // Find camera-related elements
        var all = panel.querySelectorAll('*');
        result.camera_items = [];
        for (var el of all) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            var cls = (el.className || '').toLowerCase();
            if ((cls.includes('camera') || cls.includes('motion')) && r.width > 20 && r.height > 10 && t) {
                result.camera_items.push({
                    text: t.substring(0, 50), x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName, cls: cls.substring(0, 50)
                });
            }
        }
        // Get all visible icons/thumbnails in the camera area
        var imgs = panel.querySelectorAll('img, svg');
        result.images = [];
        for (var img of imgs) {
            var r2 = img.getBoundingClientRect();
            if (r2.y > 400 && r2.width > 20) {
                result.images.push({
                    x: Math.round(r2.x), y: Math.round(r2.y),
                    w: Math.round(r2.width), h: Math.round(r2.height),
                    src: (img.src || '').substring(0, 80),
                    alt: img.alt || ''
                });
            }
        }
        // Full bottom text
        result.bottom_text = panel.innerText.substring(panel.innerText.length - 500);
        return result;
    }""")
    print(f"  Camera items: {json.dumps(camera.get('camera_items', []), indent=2)}")
    print(f"  Camera images: {len(camera.get('images', []))}")
    print(f"  Bottom text:")
    for line in camera.get('bottom_text', '').split('\n'):
        if line.strip():
            print(f"    {line.strip()}")

    # Try clicking individual camera motion presets
    print("\n[34f] Mapping camera motion grid...")
    # Camera section typically has a grid of motion presets
    motions = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        // Look for clickable items in the camera section
        var items = panel.querySelectorAll('.camera-motion-item, [class*="camera"] .item, [class*="camera"] button, [class*="camera"] div[class*="item"]');
        var result = [];
        for (var item of items) {
            var r = item.getBoundingClientRect();
            var t = (item.innerText || '').trim();
            if (r.width > 20 && r.height > 20 && r.y > 100) {
                result.push({
                    text: t.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (item.className || '').substring(0, 40),
                    title: item.title || ''
                });
            }
        }
        return result;
    }""")
    print(f"  Motion presets: {json.dumps(motions, indent=2)}")

    # Now switch to "Start and Last" and "AnyFrame" tabs to see differences
    print("\n[34g] Exploring AnyFrame mode...")
    click_in_panel(page, "AnyFrame", wait=1500)
    ss(page, "p165_anyframe")
    anyframe = get_panel_text(page)
    print("  AnyFrame panel:")
    for line in anyframe.split('\n')[:20]:
        if line.strip():
            print(f"    {line.strip()}")

    # Map AnyFrame upload slots
    anyframe_details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {};
        var uploads = panel.querySelectorAll('.pick-image, .upload-image-btn');
        var result = {uploads: []};
        for (var u of uploads) {
            var r = u.getBoundingClientRect();
            result.uploads.push({
                text: (u.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                cls: (u.className || '').substring(0, 40),
                disabled: u.className.includes('disabled')
            });
        }
        return result;
    }""")
    print(f"  AnyFrame uploads: {json.dumps(anyframe_details, indent=2)}")

    # Go back to Key Frame > Start and Last
    click_in_panel(page, "Start and Last", wait=1000)


# ======================================================================
# TASK 35: Image Editor Sub-Tools
# ======================================================================

def task_35_image_editor(page):
    print("\n" + "=" * 70)
    print("TASK 35: Image Editor — All Sub-Tools Deep Dive")
    print("=" * 70)

    ensure_canvas(page)

    # Open Image Editor (y=698)
    print("\n[35a] Opening Image Editor...")
    click_tool(page, 698, wait=2500)

    # Verify
    panel = get_panel_text(page)
    print(f"  Panel starts with: {panel[:100]}")
    if "Image Editor" not in panel and "Local Edit" not in panel:
        print("  WARNING: Not in Image Editor. Panel content:")
        for line in panel.split('\n')[:10]:
            if line.strip():
                print(f"    {line.strip()}")

    ss(page, "p166_image_editor_main")

    # Map all sub-tools by finding collapse-option elements
    print("\n[35b] Mapping all Image Editor sub-tools...")
    sub_tools = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel', url: location.href};
        var options = panel.querySelectorAll('.collapse-option');
        var result = [];
        for (var opt of options) {
            var r = opt.getBoundingClientRect();
            var t = (opt.innerText || '').trim();
            if (t && r.width > 50) {
                result.push({
                    text: t.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (opt.className || '').substring(0, 50)
                });
            }
        }
        // Also get section headers
        var headers = panel.querySelectorAll('.collapse-title, .section-title, h3, h4');
        var sections = [];
        for (var h of headers) {
            var ht = (h.innerText || '').trim();
            if (ht) sections.push(ht);
        }
        return {sub_tools: result, sections: sections, full_text: panel.innerText.substring(0, 1000)};
    }""")
    print(f"  Sections: {sub_tools.get('sections', [])}")
    print(f"  Sub-tools ({len(sub_tools.get('sub_tools', []))}):")
    for st in sub_tools.get('sub_tools', []):
        print(f"    ({st['x']},{st['y']}) {st['w']}x{st['h']} '{st['text']}' cls={st['cls']}")

    # Scroll panel to see all options
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) panel.scrollTop = panel.scrollHeight;
    }""")
    page.wait_for_timeout(500)
    ss(page, "p166_image_editor_scrolled")

    scrolled = get_panel_text(page)
    if scrolled != panel:
        print(f"\n  Scrolled panel (new content):")
        for line in scrolled.split('\n'):
            l = line.strip()
            if l and l not in panel:
                print(f"    {l}")

    # Click each sub-tool one by one
    tool_names = ["Product Background", "Generative Expand", "Expand", "AI Eraser", "Hand Repair", "Face Swap", "Face Repair", "Expression Edit", "Sketch"]

    for tool_name in tool_names:
        print(f"\n[35c] Exploring '{tool_name}'...")
        # Scroll to top
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) panel.scrollTop = 0;
        }""")
        page.wait_for_timeout(300)

        # Find and click the collapse-option
        found = page.evaluate(f"""() => {{
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {{found: false, reason: 'no panel'}};
            var options = panel.querySelectorAll('.collapse-option');
            for (var opt of options) {{
                var t = (opt.innerText || '').trim();
                if (t.includes('{tool_name}')) {{
                    opt.click();
                    var r = opt.getBoundingClientRect();
                    return {{found: true, text: t.substring(0, 40), x: Math.round(r.x), y: Math.round(r.y)}};
                }}
            }}
            // Try scrolled
            panel.scrollTop = panel.scrollHeight / 2;
            options = panel.querySelectorAll('.collapse-option');
            for (var opt of options) {{
                var t2 = (opt.innerText || '').trim();
                if (t2.includes('{tool_name}')) {{
                    opt.click();
                    return {{found: true, text: t2.substring(0, 40), scrolled: true}};
                }}
            }}
            panel.scrollTop = panel.scrollHeight;
            options = panel.querySelectorAll('.collapse-option');
            for (var opt of options) {{
                var t3 = (opt.innerText || '').trim();
                if (t3.includes('{tool_name}')) {{
                    opt.click();
                    return {{found: true, text: t3.substring(0, 40), scrolled: 'bottom'}};
                }}
            }}
            return {{found: false}};
        }}""")
        print(f"    Click: {json.dumps(found)}")

        if found.get("found"):
            page.wait_for_timeout(2000)
            close_dialogs(page)

            safe = tool_name.lower().replace(" ", "_")
            ss(page, f"p166_{safe}")

            # Map the sub-tool panel
            sub_panel = get_panel_text(page)
            print(f"    Panel text:")
            for line in sub_panel.split('\n')[:20]:
                if line.strip():
                    print(f"      {line.strip()}")

            # Map specific controls
            controls = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                var result = {};
                // Textareas
                var tas = panel.querySelectorAll('textarea, .custom-textarea');
                result.textareas = [];
                for (var ta of tas) {
                    var r = ta.getBoundingClientRect();
                    if (r.width > 50 && r.y > 50) {
                        result.textareas.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            placeholder: (ta.placeholder || ta.dataset.placeholder || '').substring(0, 80),
                            maxlen: ta.maxLength || 0
                        });
                    }
                }
                // Uploads
                var uploads = panel.querySelectorAll('.pick-image, .upload-image-btn');
                result.uploads = [];
                for (var u of uploads) {
                    var r2 = u.getBoundingClientRect();
                    if (r2.width > 20 && r2.y > 50) {
                        result.uploads.push({
                            text: (u.innerText || '').trim().substring(0, 40),
                            x: Math.round(r2.x), y: Math.round(r2.y),
                            w: Math.round(r2.width)
                        });
                    }
                }
                // Sliders
                result.sliders = panel.querySelectorAll('.c-slider, input[type="range"]').length;
                // Generate button
                var gen = panel.querySelector('.generative');
                if (gen) {
                    result.generate = {
                        text: (gen.innerText || '').trim().substring(0, 20),
                        disabled: gen.disabled || gen.className.includes('disabled')
                    };
                }
                return result;
            }""")
            print(f"    Controls: {json.dumps(controls, indent=2)}")

            # Go back to Image Editor main
            page.evaluate("""() => {
                var back = document.querySelector('.c-gen-config.show .ico-back') ||
                           document.querySelector('.c-gen-config.show .back') ||
                           document.querySelector('.c-gen-config.show [class*="back"]:not(.background)');
                if (back) { back.click(); return 'back'; }
                return 'no back button';
            }""")
            page.wait_for_timeout(1000)

            # If we didn't go back, reopen Image Editor
            current = get_panel_text(page)
            if "Image Editor" not in current and "Local Edit" not in current:
                click_tool(page, 698, wait=2000)


# ======================================================================
# TASK 37: Advanced Settings (Txt2Img + Img2Img)
# ======================================================================

def task_37_advanced(page):
    print("\n" + "=" * 70)
    print("TASK 37: Txt2Img/Img2Img Advanced Settings")
    print("=" * 70)

    ensure_canvas(page)

    # Open Txt2Img
    print("\n[37a] Opening Txt2Img...")
    click_tool(page, 197, wait=2000)

    # Click Advanced to expand
    print("\n[37b] Expanding Advanced section...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var btns = panel.querySelectorAll('.advanced-btn, button');
        for (var btn of btns) {
            if ((btn.innerText || '').trim() === 'Advanced') {
                btn.click();
                return true;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    ss(page, "p167_txt2img_advanced")

    # Map Advanced panel contents
    advanced = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        // Scroll to bottom to show advanced section
        panel.scrollTop = panel.scrollHeight;
        var result = {};
        // All inputs
        var inputs = panel.querySelectorAll('input');
        result.inputs = [];
        for (var inp of inputs) {
            var r = inp.getBoundingClientRect();
            if (r.width > 30 && r.y > 50) {
                result.inputs.push({
                    type: inp.type, value: inp.value,
                    placeholder: inp.placeholder || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                    cls: (inp.className || '').substring(0, 30)
                });
            }
        }
        // All textareas (including negative prompt)
        var tas = panel.querySelectorAll('textarea');
        result.textareas = [];
        for (var ta of tas) {
            var r2 = ta.getBoundingClientRect();
            result.textareas.push({
                x: Math.round(r2.x), y: Math.round(r2.y),
                w: Math.round(r2.width), h: Math.round(r2.height),
                placeholder: (ta.placeholder || '').substring(0, 80),
                value: (ta.value || '').substring(0, 40),
                maxlen: ta.maxLength || 0
            });
        }
        // Switches in advanced area
        var switches = panel.querySelectorAll('.c-switch');
        result.switches = [];
        for (var sw of switches) {
            var r3 = sw.getBoundingClientRect();
            if (r3.y > 500) {  // Only advanced area
                var p = sw.parentElement;
                var label = '';
                if (p) {
                    for (var c of p.childNodes) {
                        if (c !== sw && c.textContent) label += c.textContent.trim() + ' ';
                    }
                }
                result.switches.push({
                    label: label.trim().substring(0, 30),
                    x: Math.round(r3.x), y: Math.round(r3.y),
                    checked: sw.className.includes('isChecked')
                });
            }
        }
        // Full panel text
        result.full_text = panel.innerText;
        return result;
    }""")

    print(f"\n[37c] Txt2Img Advanced:")
    print(f"  Inputs: {json.dumps(advanced.get('inputs', []), indent=2)}")
    print(f"  Textareas: {json.dumps(advanced.get('textareas', []), indent=2)}")
    print(f"  Switches: {json.dumps(advanced.get('switches', []), indent=2)}")

    full = advanced.get('full_text', '')
    print(f"\n  Full panel text:")
    for line in full.split('\n'):
        if line.strip():
            print(f"    {line.strip()}")

    ss(page, "p167_txt2img_advanced_scrolled")

    # Now check Img2Img Advanced
    print("\n[37d] Opening Img2Img...")
    click_tool(page, 252, wait=2000)

    # Expand Advanced
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var btns = panel.querySelectorAll('.advanced-btn, button');
        for (var btn of btns) {
            if ((btn.innerText || '').trim() === 'Advanced') {
                btn.click();
                return true;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    ss(page, "p167_img2img_advanced")

    img2img_adv = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {};
        panel.scrollTop = panel.scrollHeight;
        var result = {full_text: panel.innerText};
        // Inputs
        var inputs = panel.querySelectorAll('input');
        result.inputs = [];
        for (var inp of inputs) {
            var r = inp.getBoundingClientRect();
            if (r.width > 30 && r.y > 50) {
                result.inputs.push({
                    type: inp.type, placeholder: inp.placeholder || '',
                    x: Math.round(r.x), y: Math.round(r.y)
                });
            }
        }
        return result;
    }""")

    print(f"\n[37e] Img2Img Advanced:")
    full2 = img2img_adv.get('full_text', '')
    for line in full2.split('\n'):
        if line.strip():
            print(f"    {line.strip()}")
    print(f"  Inputs: {json.dumps(img2img_adv.get('inputs', []), indent=2)}")

    ss(page, "p167_img2img_advanced_scrolled")

    # Explore Describe Canvas button
    print("\n[37f] Testing Describe Canvas button...")
    dc = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {found: false};
        var btn = panel.querySelector('.autoprompt, button:has-text("Describe Canvas")');
        if (btn) {
            var r = btn.getBoundingClientRect();
            return {found: true, text: (btn.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y),
                    disabled: btn.disabled, cls: (btn.className || '').substring(0, 40)};
        }
        // Search by text
        var all = panel.querySelectorAll('button, div[class*="auto"]');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            if (t.includes('Describe Canvas') || t.includes('Describe')) {
                var r2 = el.getBoundingClientRect();
                return {found: true, text: t, x: Math.round(r2.x), y: Math.round(r2.y)};
            }
        }
        return {found: false};
    }""")
    print(f"  Describe Canvas: {json.dumps(dc, indent=2)}")


# ======================================================================
# MAIN
# ======================================================================

def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 3 — Tasks 34, 35, 37")
    print("=" * 70)

    pw, browser, page = connect()
    print(f"Connected to Brave. Current URL: {page.url}")

    try:
        task_34_video_models_camera(page)
        task_35_image_editor(page)
        task_37_advanced(page)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        ss(page, "p16x_error")
    finally:
        print("\n" + "=" * 70)
        print("EXPLORATION PART 3 COMPLETE")
        print("=" * 70)


if __name__ == "__main__":
    main()
