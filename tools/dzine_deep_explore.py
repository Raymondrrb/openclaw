#!/usr/bin/env python3
"""Dzine Deep Exploration — Phases 153-156.

Connects to Brave via CDP and systematically maps unexplored Dzine features:
- Phase 153: Product Background tool (Image Editor sub-tool)
- Phase 154: Local Edit (inpainting) + Insert Object
- Phase 155: Seedance 2.0 video model deep-dive
- Phase 156: Style Creation (Quick Style + Pro Style)

Saves screenshots to ~/Downloads/p15X_*.png and prints structured findings.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright


CANVAS_URL = "https://www.dzine.ai/canvas?id=19861203"
HOME_URL = "https://www.dzine.ai/home"
CDP_PORT = 18800
DOWNLOADS = Path.home() / "Downloads"


def connect():
    """Connect to running Brave via CDP."""
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    return pw, browser, page


def close_dialogs(page, rounds=8):
    """Dismiss popups."""
    for _ in range(rounds):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click(timeout=1000)
                    found = True
                    page.wait_for_timeout(300)
            except Exception:
                pass
        if not found:
            break


def screenshot(page, name):
    """Save screenshot."""
    path = DOWNLOADS / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  Screenshot: {path}")


def map_elements(page, selector, label="", max_items=50):
    """Map interactive elements matching selector."""
    items = page.evaluate(f"""() => {{
        var els = document.querySelectorAll('{selector}');
        var results = [];
        for (var i = 0; i < Math.min(els.length, {max_items}); i++) {{
            var el = els[i];
            var r = el.getBoundingClientRect();
            results.push({{
                tag: el.tagName,
                text: (el.innerText || '').trim().substring(0, 60),
                cls: (el.className || '').substring(0, 80),
                x: Math.round(r.x),
                y: Math.round(r.y),
                w: Math.round(r.width),
                h: Math.round(r.height),
                disabled: el.disabled || false,
            }});
        }}
        return results;
    }}""")
    if label:
        print(f"\n[{label}] Found {len(items)} elements:")
    for it in items:
        d = " [DISABLED]" if it.get("disabled") else ""
        print(f"  ({it['x']},{it['y']}) {it['w']}x{it['h']} <{it['tag']}> '{it['text'][:50]}' cls={it['cls'][:50]}{d}")
    return items


def map_panel_text(page, label=""):
    """Extract all text from the active panel."""
    text = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.panels.show');
        if (!panel) return 'NO PANEL FOUND';
        return panel.innerText;
    }""")
    if label:
        print(f"\n[{label}] Panel text:")
        for line in text.split('\n')[:40]:
            if line.strip():
                print(f"  {line.strip()}")
    return text


def map_buttons(page, label=""):
    """Map all visible buttons in the active panel."""
    return map_elements(page, '.c-gen-config.show button, .panels.show button, .collapse-panel button', label)


def ensure_canvas(page):
    """Navigate to canvas if not there."""
    if "canvas" not in (page.url or ""):
        page.goto(CANVAS_URL)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        page.wait_for_timeout(1000)


def click_sidebar(page, y, wait_ms=2000):
    """Click a sidebar tool."""
    page.mouse.click(40, y)
    page.wait_for_timeout(wait_ms)
    close_dialogs(page)


# ======================================================================
# PHASE 153: Product Background Tool
# ======================================================================

def phase_153_product_background(page):
    print("\n" + "=" * 70)
    print("PHASE 153: Product Background Tool (Image Editor)")
    print("=" * 70)

    ensure_canvas(page)

    # Open Image Editor
    print("\n[153a] Opening Image Editor (y=698)...")
    click_sidebar(page, 698)
    map_panel_text(page, "ImageEditor")

    # Scroll down to find Product Background
    print("\n[153b] Looking for Product Background sub-tool...")
    # Product Background is at the bottom of Image Editor panel
    result = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {found: false, text: 'no panel'};
        // Scroll the panel to bottom
        panel.scrollTop = panel.scrollHeight;
        // Find Product Background option
        var options = panel.querySelectorAll('.collapse-option, button');
        for (var opt of options) {
            var t = (opt.innerText || '').trim();
            if (t.includes('Product Background') || t.includes('Background')) {
                var r = opt.getBoundingClientRect();
                return {found: true, text: t, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height), cls: opt.className};
            }
        }
        return {found: false, text: 'not found in ' + panel.innerText.substring(0, 200)};
    }""")
    print(f"  Product Background: {json.dumps(result, indent=2)}")

    if result.get("found"):
        # Click it
        print("\n[153c] Clicking Product Background...")
        page.mouse.click(result["x"] + result["w"] // 2, result["y"] + result["h"] // 2)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        screenshot(page, "p153_product_bg_panel")
        map_panel_text(page, "ProductBG")
        map_buttons(page, "ProductBG buttons")

        # Look for template categories, prompt input, generate button
        print("\n[153d] Mapping Product Background UI details...")
        details = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {error: 'no panel'};
            var result = {};
            // Find textarea/prompt
            var ta = panel.querySelector('textarea, [contenteditable="true"]');
            if (ta) {
                var r = ta.getBoundingClientRect();
                result.prompt = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                                 placeholder: ta.placeholder || '', maxlen: ta.maxLength || 0};
            }
            // Find template thumbnails
            var thumbs = panel.querySelectorAll('img[src*="template"], .template-item, .scene-item');
            result.templates = thumbs.length;
            // Find generate button
            var gen = panel.querySelector('.generative, button:has(.generative)');
            if (gen) {
                var r2 = gen.getBoundingClientRect();
                result.generate = {x: Math.round(r2.x), y: Math.round(r2.y),
                                   text: (gen.innerText || '').trim().substring(0, 40),
                                   disabled: gen.disabled || false, cls: gen.className};
            }
            // Find upload area
            var upload = panel.querySelector('.upload-image-btn, .pick-image, button:has-text("upload")');
            if (upload) {
                var r3 = upload.getBoundingClientRect();
                result.upload = {x: Math.round(r3.x), y: Math.round(r3.y),
                                 text: (upload.innerText || '').trim().substring(0, 40)};
            }
            // Collect all section titles
            var titles = panel.querySelectorAll('.title, h3, h4, .group');
            result.sections = [];
            for (var t of titles) {
                var txt = (t.innerText || '').trim();
                if (txt) result.sections.push(txt);
            }
            return result;
        }""")
        print(f"  Details: {json.dumps(details, indent=2)}")

        # Try scrolling the panel to see all content
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) panel.scrollTop = 0;
        }""")
        page.wait_for_timeout(500)
        screenshot(page, "p153_product_bg_top")

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) panel.scrollTop = panel.scrollHeight;
        }""")
        page.wait_for_timeout(500)
        screenshot(page, "p153_product_bg_bottom")
    else:
        print("  WARNING: Product Background not found, trying alternative approach...")
        # Try clicking by scrolling panel and looking for it
        screenshot(page, "p153_image_editor_full")

    # Close panel
    click_sidebar(page, 197)  # Switch to Txt2Img to reset
    page.wait_for_timeout(500)


# ======================================================================
# PHASE 154: Local Edit (Inpainting) + Insert Object
# ======================================================================

def phase_154_local_edit(page):
    print("\n" + "=" * 70)
    print("PHASE 154: Local Edit (Inpainting) + Insert Object")
    print("=" * 70)

    ensure_canvas(page)

    # Open Image Editor
    print("\n[154a] Opening Image Editor (y=698)...")
    click_sidebar(page, 698)
    page.wait_for_timeout(1500)

    # Click Local Edit
    print("\n[154b] Clicking Local Edit...")
    result = page.evaluate("""() => {
        var options = document.querySelectorAll('.collapse-option');
        for (var opt of options) {
            if ((opt.innerText || '').includes('Local Edit')) {
                opt.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked: {result}")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    screenshot(page, "p154_local_edit_panel")
    map_panel_text(page, "LocalEdit")
    map_buttons(page, "LocalEdit buttons")

    # Map selection tools and prompt area
    print("\n[154c] Mapping Local Edit UI...")
    details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Selection mode buttons (Lasso, Brush, Auto)
        var items = panel.querySelectorAll('.item');
        result.selection_modes = [];
        for (var item of items) {
            var t = (item.innerText || '').trim();
            var r = item.getBoundingClientRect();
            if (t && r.width > 20 && r.width < 200) {
                result.selection_modes.push({
                    text: t, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), cls: item.className
                });
            }
        }
        // Prompt textarea
        var ta = panel.querySelector('textarea, [contenteditable="true"], .custom-textarea');
        if (ta) {
            var r2 = ta.getBoundingClientRect();
            result.prompt = {x: Math.round(r2.x), y: Math.round(r2.y),
                            w: Math.round(r2.width), h: Math.round(r2.height),
                            placeholder: ta.placeholder || ta.dataset.placeholder || '',
                            maxlen: ta.maxLength || 0};
        }
        // Invert/Clear buttons
        var btns = panel.querySelectorAll('button');
        result.action_buttons = [];
        for (var btn of btns) {
            var t2 = (btn.innerText || '').trim();
            var cls = btn.className || '';
            if (cls.includes('invert') || cls.includes('clear') || t2 === 'Invert' || t2 === 'Clear') {
                var r3 = btn.getBoundingClientRect();
                result.action_buttons.push({
                    text: t2 || cls, x: Math.round(r3.x), y: Math.round(r3.y)
                });
            }
        }
        // Generate button
        var gen = panel.querySelector('.generative');
        if (gen) {
            var r4 = gen.getBoundingClientRect();
            result.generate = {x: Math.round(r4.x), y: Math.round(r4.y),
                              text: (gen.innerText || '').trim().substring(0, 40),
                              disabled: gen.disabled};
        }
        // Sliders
        var sliders = panel.querySelectorAll('.c-slider, input[type="range"]');
        result.sliders = sliders.length;
        return result;
    }""")
    print(f"  Details: {json.dumps(details, indent=2)}")

    # Now explore Insert Object
    print("\n[154d] Going back to Image Editor...")
    # Click the back/close button to return to Image Editor overview
    page.evaluate("""() => {
        var back = document.querySelector('.c-gen-config.show .back, .c-gen-config.show .ico-close');
        if (back) { back.click(); return 'back'; }
        return 'no back button';
    }""")
    page.wait_for_timeout(1000)
    click_sidebar(page, 698)
    page.wait_for_timeout(1500)

    print("\n[154e] Clicking Insert Object...")
    result = page.evaluate("""() => {
        var options = document.querySelectorAll('.collapse-option');
        for (var opt of options) {
            if ((opt.innerText || '').includes('Insert Object')) {
                opt.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked: {result}")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    screenshot(page, "p154_insert_object_panel")
    map_panel_text(page, "InsertObject")
    map_buttons(page, "InsertObject buttons")

    # Map Insert Object UI
    print("\n[154f] Mapping Insert Object UI...")
    details2 = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Prompt
        var ta = panel.querySelector('textarea, [contenteditable="true"], .custom-textarea');
        if (ta) {
            var r = ta.getBoundingClientRect();
            result.prompt = {x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            placeholder: ta.placeholder || ta.dataset.placeholder || ''};
        }
        // Reference image upload
        var uploads = panel.querySelectorAll('.pick-image, .upload-image-btn, button.image-item');
        result.uploads = [];
        for (var u of uploads) {
            var r2 = u.getBoundingClientRect();
            result.uploads.push({
                text: (u.innerText || '').trim().substring(0, 40),
                x: Math.round(r2.x), y: Math.round(r2.y),
                cls: u.className.substring(0, 50)
            });
        }
        // Selection tools
        var items = panel.querySelectorAll('.item');
        result.tools = [];
        for (var item of items) {
            var t = (item.innerText || '').trim();
            var r3 = item.getBoundingClientRect();
            if (t && r3.width > 20 && r3.width < 200 && r3.y > 100) {
                result.tools.push({text: t, x: Math.round(r3.x), y: Math.round(r3.y),
                                   active: item.className.includes('active')});
            }
        }
        // Generate
        var gen = panel.querySelector('.generative');
        if (gen) {
            var r4 = gen.getBoundingClientRect();
            result.generate = {text: (gen.innerText || '').trim().substring(0, 40),
                              x: Math.round(r4.x), y: Math.round(r4.y), disabled: gen.disabled};
        }
        return result;
    }""")
    print(f"  Details: {json.dumps(details2, indent=2)}")

    # Reset
    click_sidebar(page, 197)
    page.wait_for_timeout(500)


# ======================================================================
# PHASE 155: Seedance 2.0 Video Deep-Dive
# ======================================================================

def phase_155_seedance(page):
    print("\n" + "=" * 70)
    print("PHASE 155: Seedance 2.0 Video Generation Deep-Dive")
    print("=" * 70)

    ensure_canvas(page)

    # Open AI Video panel
    print("\n[155a] Opening AI Video panel (y=361)...")
    click_sidebar(page, 361)
    page.wait_for_timeout(2000)

    screenshot(page, "p155_ai_video_panel")
    map_panel_text(page, "AIVideo")

    # Open model selector and find Seedance 2.0
    print("\n[155b] Opening model selector...")
    page.evaluate("""() => {
        var sel = document.querySelector('.custom-selector-wrapper');
        if (sel) { sel.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Find Seedance 2.0 in the model list
    print("\n[155c] Searching for Seedance 2.0...")
    models = page.evaluate("""() => {
        var panel = document.querySelector('.selector-panel');
        if (!panel) return {error: 'no selector panel'};
        var items = panel.querySelectorAll('.model-item, .item, [class*="model"]');
        var results = [];
        for (var item of items) {
            var t = (item.innerText || '').trim().substring(0, 80);
            if (t.toLowerCase().includes('seedance')) {
                var r = item.getBoundingClientRect();
                results.push({text: t, x: Math.round(r.x), y: Math.round(r.y),
                              w: Math.round(r.width), cls: item.className.substring(0, 50)});
            }
        }
        return {seedance_models: results, total_items: items.length};
    }""")
    print(f"  Seedance models: {json.dumps(models, indent=2)}")

    screenshot(page, "p155_model_selector")

    # Try to select Seedance 2.0 or Seedance Pro
    print("\n[155d] Selecting Seedance model...")
    selected = page.evaluate("""() => {
        var panel = document.querySelector('.selector-panel');
        if (!panel) return 'no panel';
        // Look for Seedance 2.0 first, then Seedance Pro
        var items = panel.querySelectorAll('.model-item, .item, [class*="model"], [class*="option"]');
        for (var name of ['Seedance 2.0', 'Seedance Pro', 'Seedance']) {
            for (var item of items) {
                var t = (item.innerText || '').trim();
                if (t.includes(name)) {
                    item.click();
                    return 'selected: ' + t.substring(0, 60);
                }
            }
        }
        // Scroll down and try again
        panel.scrollTop = 500;
        return 'not found, scrolled';
    }""")
    print(f"  {selected}")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Map the full AI Video panel after model selection
    screenshot(page, "p155_after_model_select")

    # Map detailed panel elements
    print("\n[155e] Mapping AI Video panel details...")
    details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.ai-video-panel');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Mode tabs (Key Frame / Reference)
        var tabs = panel.querySelectorAll('.options button, .tab-item, .mode-item');
        result.modes = [];
        for (var tab of tabs) {
            var t = (tab.innerText || '').trim();
            var r = tab.getBoundingClientRect();
            if (t && r.width > 30) {
                result.modes.push({text: t, x: Math.round(r.x), y: Math.round(r.y),
                                   active: tab.className.includes('selected') || tab.className.includes('active')});
            }
        }
        // Upload areas (start frame, reference)
        var uploads = panel.querySelectorAll('.pick-image, .upload-image-btn');
        result.uploads = [];
        for (var u of uploads) {
            var r2 = u.getBoundingClientRect();
            result.uploads.push({
                text: (u.innerText || '').trim().substring(0, 50),
                x: Math.round(r2.x), y: Math.round(r2.y),
                cls: u.className.substring(0, 50)
            });
        }
        // Prompt
        var ta = panel.querySelector('textarea, .custom-textarea');
        if (ta) {
            var r3 = ta.getBoundingClientRect();
            result.prompt = {x: Math.round(r3.x), y: Math.round(r3.y),
                            w: Math.round(r3.width), h: Math.round(r3.height),
                            maxlen: ta.maxLength || 0,
                            placeholder: (ta.placeholder || '').substring(0, 60)};
        }
        // Camera section
        var cameras = panel.querySelectorAll('[class*="camera"], [class*="Camera"]');
        result.camera_elements = cameras.length;
        // Settings (resolution, duration, aspect ratio)
        var allText = panel.innerText;
        result.has_resolution = allText.includes('Resolution') || allText.includes('resolution');
        result.has_duration = allText.includes('Duration') || allText.includes('duration');
        result.has_aspect = allText.includes('Aspect') || allText.includes('aspect');
        result.has_camera = allText.includes('Camera') || allText.includes('camera');
        // @ mention support
        result.has_at_mention = allText.includes('@') || allText.includes('mention');
        // Generate button
        var gen = panel.querySelector('.generative');
        if (gen) {
            var r4 = gen.getBoundingClientRect();
            result.generate = {text: (gen.innerText || '').trim().substring(0, 40),
                              x: Math.round(r4.x), y: Math.round(r4.y),
                              disabled: gen.disabled, cls: gen.className.substring(0, 50)};
        }
        return result;
    }""")
    print(f"  Details: {json.dumps(details, indent=2)}")

    # Explore Reference mode
    print("\n[155f] Switching to Reference mode...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var btns = panel.querySelectorAll('button, .options div');
        for (var btn of btns) {
            if ((btn.innerText || '').trim() === 'Reference') {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)

    screenshot(page, "p155_reference_mode")
    map_panel_text(page, "ReferenceMode")

    # Map reference mode details (@ mention input)
    print("\n[155g] Mapping Reference mode details...")
    ref_details = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var result = {};
        // Multiple upload slots
        var uploads = panel.querySelectorAll('.pick-image, .upload-image-btn, .image-item');
        result.upload_slots = [];
        for (var u of uploads) {
            var r = u.getBoundingClientRect();
            var t = (u.innerText || '').trim().substring(0, 50);
            if (r.width > 20 && r.y > 50) {
                result.upload_slots.push({text: t, x: Math.round(r.x), y: Math.round(r.y),
                                          w: Math.round(r.width), h: Math.round(r.height)});
            }
        }
        // Prompt with @ support
        var ta = panel.querySelector('textarea, .custom-textarea');
        if (ta) {
            var r2 = ta.getBoundingClientRect();
            result.prompt = {x: Math.round(r2.x), y: Math.round(r2.y),
                            value: (ta.value || ta.innerText || '').substring(0, 100)};
        }
        // All visible text (for understanding layout)
        result.panel_text = panel.innerText.substring(0, 500);
        return result;
    }""")
    print(f"  Reference mode: {json.dumps(ref_details, indent=2)}")

    # Reset
    click_sidebar(page, 197)
    page.wait_for_timeout(500)


# ======================================================================
# PHASE 156: Style Creation (Quick Style + Pro Style)
# ======================================================================

def phase_156_style_creation(page):
    print("\n" + "=" * 70)
    print("PHASE 156: Style Creation (Quick Style + Pro Style)")
    print("=" * 70)

    ensure_canvas(page)

    # Open Txt2Img and click style button
    print("\n[156a] Opening Txt2Img + style picker...")
    click_sidebar(page, 252)  # Img2Img first
    page.wait_for_timeout(500)
    click_sidebar(page, 197)  # Then Txt2Img
    page.wait_for_timeout(1500)

    # Open style picker
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    # Find and click "Create a style"
    print("\n[156b] Looking for style creation options...")
    create_options = page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel');
        if (!panel) return {error: 'no style panel'};
        var result = {};
        // Find "Create a style", "Quick Style", "Pro Style" buttons
        var all = panel.querySelectorAll('*');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t === 'Create a style' || t === 'Quick Style' || t === 'Pro Style') {
                if (!result[t]) {
                    result[t] = {x: Math.round(r.x), y: Math.round(r.y),
                                 w: Math.round(r.width), h: Math.round(r.height),
                                 tag: el.tagName, cls: el.className.substring(0, 50)};
                }
            }
        }
        return result;
    }""")
    print(f"  Create options: {json.dumps(create_options, indent=2)}")

    screenshot(page, "p156_style_picker_create")

    # Click "Quick Style" to explore it
    if "Quick Style" in create_options:
        qs = create_options["Quick Style"]
        print("\n[156c] Clicking Quick Style...")
        page.mouse.click(qs["x"] + qs["w"] // 2, qs["y"] + qs["h"] // 2)
        page.wait_for_timeout(3000)
        close_dialogs(page)

        screenshot(page, "p156_quick_style_panel")

        # Map Quick Style UI
        print("\n[156d] Mapping Quick Style UI...")
        qs_details = page.evaluate("""() => {
            // Look for a dialog/panel/page that appeared
            var panels = document.querySelectorAll('.modal, .dialog, [class*="style-create"], [class*="quick-style"], .c-gen-config.show');
            var result = {panels_found: panels.length};
            // Check for file upload
            var uploads = document.querySelectorAll('.pick-image, .upload-image-btn, input[type="file"]');
            result.upload_elements = uploads.length;
            // Get all visible text in new panels
            for (var p of panels) {
                var t = (p.innerText || '').trim().substring(0, 500);
                if (t.length > 10) {
                    result.panel_text = t;
                    break;
                }
            }
            // Check if we navigated to a new page
            result.url = window.location.href;
            // Get all interactive elements on the page
            var btns = document.querySelectorAll('button:not([style*="display: none"])');
            result.visible_buttons = [];
            for (var btn of btns) {
                var r = btn.getBoundingClientRect();
                if (r.width > 30 && r.height > 20 && r.y > 0 && r.y < 900) {
                    var text = (btn.innerText || '').trim().substring(0, 40);
                    if (text) {
                        result.visible_buttons.push({
                            text: text, x: Math.round(r.x), y: Math.round(r.y)
                        });
                    }
                }
            }
            return result;
        }""")
        print(f"  Quick Style: {json.dumps(qs_details, indent=2)}")

        # Go back if we navigated away
        if "canvas" not in (page.url or ""):
            print(f"  Navigated to: {page.url}")
            screenshot(page, "p156_quick_style_page")
            # Map this page thoroughly
            map_elements(page, 'button, input, textarea, .upload-area, .pick-image', "QuickStylePage")
            # Go back
            page.go_back()
            page.wait_for_timeout(2000)

    # Return to canvas and try Pro Style
    ensure_canvas(page)
    click_sidebar(page, 197)
    page.wait_for_timeout(1000)
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    if "Pro Style" in create_options:
        ps = create_options["Pro Style"]
        print("\n[156e] Clicking Pro Style...")
        page.mouse.click(ps["x"] + ps["w"] // 2, ps["y"] + ps["h"] // 2)
        page.wait_for_timeout(3000)
        close_dialogs(page)

        screenshot(page, "p156_pro_style_panel")

        # Map Pro Style page
        print("\n[156f] Mapping Pro Style UI...")
        ps_details = page.evaluate("""() => {
            var result = {url: window.location.href};
            var btns = document.querySelectorAll('button:not([style*="display: none"])');
            result.visible_buttons = [];
            for (var btn of btns) {
                var r = btn.getBoundingClientRect();
                if (r.width > 30 && r.height > 20 && r.y > 0 && r.y < 900) {
                    var text = (btn.innerText || '').trim().substring(0, 40);
                    if (text) {
                        result.visible_buttons.push({
                            text: text, x: Math.round(r.x), y: Math.round(r.y)
                        });
                    }
                }
            }
            // Upload areas
            var uploads = document.querySelectorAll('.upload-area, .pick-image, .upload-image-btn, [class*="upload"]');
            result.upload_areas = uploads.length;
            // All page text (first 500 chars)
            result.page_text = document.body.innerText.substring(0, 800);
            return result;
        }""")
        print(f"  Pro Style: {json.dumps(ps_details, indent=2)}")

        if "canvas" not in (page.url or ""):
            screenshot(page, "p156_pro_style_page")
            map_elements(page, 'button, input, textarea, .upload-area', "ProStylePage")
            page.go_back()
            page.wait_for_timeout(2000)

    # Reset
    ensure_canvas(page)
    print("\n[156] Phase 156 complete.")


# ======================================================================
# PHASE 157: Face Match + Color Match toggles deep-dive
# ======================================================================

def phase_157_face_color_match(page):
    print("\n" + "=" * 70)
    print("PHASE 157: Face Match + Color Match Toggles")
    print("=" * 70)

    ensure_canvas(page)

    # Open Txt2Img
    print("\n[157a] Opening Txt2Img...")
    click_sidebar(page, 252)
    page.wait_for_timeout(500)
    click_sidebar(page, 197)
    page.wait_for_timeout(1500)

    # Map Face Match and Color Match toggles
    print("\n[157b] Mapping Face Match / Color Match in Txt2Img...")
    toggles_txt2img = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var switches = panel.querySelectorAll('.c-switch');
        var result = [];
        for (var sw of switches) {
            var r = sw.getBoundingClientRect();
            // Get the label (previous sibling or parent text)
            var parent = sw.parentElement;
            var label = '';
            if (parent) {
                var children = parent.childNodes;
                for (var c of children) {
                    if (c !== sw && c.textContent) {
                        label += c.textContent.trim() + ' ';
                    }
                }
            }
            result.push({
                label: label.trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                checked: sw.className.includes('isChecked') || sw.className.includes('checked'),
                cls: sw.className.substring(0, 60)
            });
        }
        return result;
    }""")
    print(f"  Txt2Img toggles: {json.dumps(toggles_txt2img, indent=2)}")

    # Now check Img2Img toggles
    print("\n[157c] Opening Img2Img...")
    click_sidebar(page, 252)
    page.wait_for_timeout(1500)

    toggles_img2img = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var switches = panel.querySelectorAll('.c-switch');
        var result = [];
        for (var sw of switches) {
            var r = sw.getBoundingClientRect();
            var parent = sw.parentElement;
            var label = '';
            if (parent) {
                var children = parent.childNodes;
                for (var c of children) {
                    if (c !== sw && c.textContent) label += c.textContent.trim() + ' ';
                }
            }
            result.push({
                label: label.trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                checked: sw.className.includes('isChecked') || sw.className.includes('checked'),
                cls: sw.className.substring(0, 60)
            });
        }
        return result;
    }""")
    print(f"  Img2Img toggles: {json.dumps(toggles_img2img, indent=2)}")

    # Map Structure Match slider in Img2Img
    print("\n[157d] Mapping Structure Match slider...")
    slider = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var sliders = panel.querySelectorAll('.c-slider, input[type="range"]');
        var result = [];
        for (var s of sliders) {
            var r = s.getBoundingClientRect();
            result.push({
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                value: s.value || '',
                min: s.min || '',
                max: s.max || '',
                cls: s.className.substring(0, 50)
            });
        }
        // Get slider label text
        var labels = panel.querySelectorAll('[class*="slider"] span, .c-slider + span, .c-slider ~ span');
        result.push({labels: Array.from(labels).map(l => l.textContent.trim()).filter(t => t)});
        return result;
    }""")
    print(f"  Slider: {json.dumps(slider, indent=2)}")

    screenshot(page, "p157_img2img_toggles")

    # Reset
    click_sidebar(page, 197)
    page.wait_for_timeout(500)


# ======================================================================
# MAIN
# ======================================================================

def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION — Phases 153-157")
    print("=" * 70)

    pw, browser, page = connect()
    print(f"Connected to Brave. Current URL: {page.url}")

    try:
        phase_153_product_background(page)
        phase_154_local_edit(page)
        phase_155_seedance(page)
        phase_156_style_creation(page)
        phase_157_face_color_match(page)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        screenshot(page, "p15x_error")
    finally:
        print("\n" + "=" * 70)
        print("EXPLORATION COMPLETE")
        print("=" * 70)
        print("Check ~/Downloads/p15*.png for screenshots")


if __name__ == "__main__":
    main()
