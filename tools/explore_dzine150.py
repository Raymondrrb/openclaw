#!/usr/bin/env python3
"""Phase 150: Deep-dive — Canvas toolbar, Style catalog, Advanced settings.

Expert-level documentation of every detail.

Goals:
1. Canvas top toolbar — enumerate ALL tool buttons, their exact positions, states
2. Style picker — catalog ALL styles by category with exact names
3. Txt2Img Advanced — seed, negative prompt, all toggles and their defaults
4. Img2Img Advanced — all sliders, default values, ranges
5. Chat Editor — model costs (check if different per model)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 150: Deep-dive — Toolbar, Styles, Advanced Settings")
    print("=" * 70)

    if not is_browser_running():
        print("[P150] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P150] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P150] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Close any open panels
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
            var p = document.querySelector('.lip-sync-config-panel.show');
            if (p) { var c = p.querySelector('.ico-close'); if (c) c.click(); }
        }""")
        page.wait_for_timeout(500)

        # ============================================================
        # 1. CANVAS TOP TOOLBAR — All buttons and tools
        # ============================================================
        print(f"\n{'='*60}")
        print("1. CANVAS TOP TOOLBAR")
        print(f"{'='*60}")

        toolbar = page.evaluate("""() => {
            var items = [];
            // Scan the top bar area (y < 60)
            for (var el of document.querySelectorAll('button, [role="button"], a, .tool-item, [class*="tool"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.y < 60 && r.x > 100 && r.x < 1000) {
                    var text = (el.innerText || el.title || el.getAttribute('aria-label') || '').trim();
                    items.push({
                        text: text.substring(0, 50),
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        id: el.id || '',
                        disabled: el.disabled || false,
                        title: (el.title || '').substring(0, 50)
                    });
                }
            }
            // Deduplicate by position
            var unique = [], seen = new Set();
            for (var item of items) {
                var key = item.x + '_' + item.y;
                if (!seen.has(key)) { seen.add(key); unique.push(item); }
            }
            return unique.sort((a,b) => a.x - b.x);
        }""")
        print(f"[1] Top toolbar items: {len(toolbar)}")
        for t in toolbar:
            dis = " DISABLED" if t['disabled'] else ""
            id_info = f" id={t['id']}" if t['id'] else ""
            title_info = f" title='{t['title']}'" if t['title'] else ""
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> '{t['text'][:40]}' cls={t['cls'][:35]}{id_info}{title_info}{dis}")

        # Also scan the action bar (y~47, just below top bar — AI Eraser, Hand Repair, etc.)
        print("\n[1b] Action bar (y 40-100)...")
        actionbar = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.y >= 35 && r.y < 65 && r.x > 150 && r.x < 600) {
                    var text = (el.innerText || el.title || '').trim();
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        disabled: el.disabled || false
                    });
                }
            }
            var unique = [], seen = new Set();
            for (var item of items) {
                var key = item.x + '_' + item.y;
                if (!seen.has(key)) { seen.add(key); unique.push(item); }
            }
            return unique.sort((a,b) => a.x - b.x);
        }""")
        print(f"[1b] Action bar items: {len(actionbar)}")
        for a in actionbar:
            dis = " DISABLED" if a['disabled'] else ""
            print(f"  ({a['x']},{a['y']}) {a['w']}x{a['h']} '{a['text'][:40]}' cls={a['cls'][:35]}{dis}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p150_toolbar.png"))

        # ============================================================
        # 2. STYLE PICKER — Full catalog of all styles
        # ============================================================
        print(f"\n{'='*60}")
        print("2. STYLE PICKER — Full Catalog")
        print(f"{'='*60}")

        # Open Txt2Img panel
        page.mouse.click(40, 252)  # Img2Img first
        page.wait_for_timeout(500)
        page.mouse.click(40, 197)  # Then Txt2Img
        page.wait_for_timeout(2000)

        # Click style button to open picker
        page.evaluate("""() => {
            var btn = document.querySelector('button.style') || document.querySelector('.style-name');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p150_style_picker.png"))

        # Get all categories (tabs)
        categories = page.evaluate("""() => {
            var cats = [];
            for (var el of document.querySelectorAll('.style-list-panel [class*="tab"], .style-list-panel [class*="category"], .style-list-panel button')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.x > 350 && r.x < 800 && r.y > 50 && r.y < 130 && text.length > 0 && text.length < 30) {
                    cats.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        cls: (el.className || '').substring(0, 40),
                        selected: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            // Deduplicate
            var unique = [], seen = new Set();
            for (var c of cats) {
                if (!seen.has(c.text)) { seen.add(c.text); unique.push(c); }
            }
            return unique;
        }""")
        print(f"[2] Style categories: {len(categories)}")
        for c in categories:
            sel = " [SELECTED]" if c['selected'] else ""
            print(f"  ({c['x']},{c['y']}) w={c['w']} '{c['text']}'{sel}")

        # Get all visible styles in current category
        all_styles = []

        def get_visible_styles():
            return page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('[class*="style-item"], [class*="style-card"]')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.width > 20 && r.height > 20 && r.x > 350 && text.length > 0) {
                        items.push({
                            text: text.substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 50)
                        });
                    }
                }
                return items;
            }""")

        # Click each category and extract styles
        for cat in categories[:15]:
            print(f"\n[2] Category: {cat['text']}")
            page.mouse.click(cat['x'] + cat['w'] // 2, cat['y'] + 10)
            page.wait_for_timeout(1500)

            styles = get_visible_styles()
            print(f"  Visible styles: {len(styles)}")
            for s in styles[:20]:
                name = s['text'].split('\n')[0].strip()
                all_styles.append(f"{cat['text']}: {name}")
                print(f"    '{name}'")

            # Scroll down to see more styles
            page.evaluate("""() => {
                var container = document.querySelector('.style-list-panel');
                if (container) {
                    var scrollable = null;
                    for (var el of container.querySelectorAll('*')) {
                        var s = window.getComputedStyle(el);
                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 50) {
                            scrollable = el;
                            break;
                        }
                    }
                    if (scrollable) {
                        scrollable.scrollTop = scrollable.scrollHeight;
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(800)

            more_styles = get_visible_styles()
            new_count = 0
            for s in more_styles:
                name = s['text'].split('\n')[0].strip()
                full = f"{cat['text']}: {name}"
                if full not in all_styles:
                    all_styles.append(full)
                    new_count += 1
                    print(f"    '{name}' (scrolled)")
            if new_count > 0:
                print(f"  +{new_count} after scroll")

        print(f"\n[2] TOTAL styles found: {len(all_styles)}")

        # Close style picker
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # 3. TXT2IMG ADVANCED SETTINGS
        # ============================================================
        print(f"\n{'='*60}")
        print("3. TXT2IMG ADVANCED SETTINGS")
        print(f"{'='*60}")

        # Click Advanced button
        page.evaluate("""() => {
            var btn = document.querySelector('.advanced-btn');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(1000)

        advanced = page.evaluate("""() => {
            var items = [];
            // Find all form elements in the gen-config panel
            for (var el of document.querySelectorAll('.c-gen-config.show input, .c-gen-config.show textarea, .c-gen-config.show select, .c-gen-config.show .c-switch, .c-gen-config.show .c-slider')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x > 60 && r.x < 400) {
                    var label = '';
                    // Find nearby label
                    var prev = el.previousElementSibling;
                    if (prev && prev.tagName !== 'INPUT') label = (prev.innerText || '').trim().substring(0, 40);
                    var parent = el.parentElement;
                    if (!label && parent) {
                        var parentLabel = parent.querySelector('label, .label, [class*="label"]');
                        if (parentLabel) label = (parentLabel.innerText || '').trim().substring(0, 40);
                    }

                    items.push({
                        tag: el.tagName,
                        type: el.type || '',
                        value: (el.value || '').substring(0, 50),
                        placeholder: (el.placeholder || '').substring(0, 50),
                        checked: el.checked || false,
                        label: label,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        print(f"[3] Advanced form elements: {len(advanced)}")
        for a in advanced:
            val_info = f" value='{a['value']}'" if a['value'] else ""
            ph_info = f" placeholder='{a['placeholder']}'" if a['placeholder'] else ""
            chk_info = " CHECKED" if a['checked'] else ""
            label = f" label='{a['label']}'" if a['label'] else ""
            print(f"  ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> type={a['type']} cls={a['cls'][:30]}{label}{val_info}{ph_info}{chk_info}")

        # Read all text content in advanced area
        adv_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) return panel.innerText.substring(0, 3000);
            return '';
        }""")
        print(f"\n[3b] Full panel text:\n{adv_text[:2000]}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p150_txt2img_advanced.png"))

        # ============================================================
        # 4. IMG2IMG PANEL — Full details
        # ============================================================
        print(f"\n{'='*60}")
        print("4. IMG2IMG PANEL DETAILS")
        print(f"{'='*60}")

        # Switch to Img2Img
        page.mouse.click(40, 197)  # Toggle away
        page.wait_for_timeout(500)
        page.mouse.click(40, 252)  # Img2Img
        page.wait_for_timeout(2000)

        img2img_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) return panel.innerText.substring(0, 3000);
            return '';
        }""")
        print(f"[4] Img2Img panel text:\n{img2img_text[:2000]}")

        # Get slider values and ranges
        sliders = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.c-gen-config.show .c-slider, .c-gen-config.show input[type="range"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0) {
                    // Find nearby label
                    var parent = el.closest('[class*="row"], [class*="item"], [class*="option"]');
                    var label = '';
                    if (parent) {
                        var lbl = parent.querySelector('.label, [class*="label"], span:first-child');
                        if (lbl) label = (lbl.innerText || '').trim();
                    }
                    items.push({
                        label: label.substring(0, 40),
                        value: el.value || '',
                        min: el.min || '',
                        max: el.max || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        cls: (el.className || '').substring(0, 40)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[4b] Sliders: {len(sliders)}")
        for s in sliders:
            print(f"  ({s['x']},{s['y']}) w={s['w']} '{s['label']}' value={s['value']} range=[{s['min']}-{s['max']}]")

        # Get all toggles/switches
        toggles = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.c-gen-config.show .c-switch, .c-gen-config.show [class*="toggle"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0) {
                    var isOn = el.className.includes('active') || el.className.includes('on') || el.className.includes('checked');
                    var parent = el.closest('[class*="row"], [class*="item"]');
                    var label = '';
                    if (parent) {
                        var lbl = parent.querySelector('.label, [class*="label"], span');
                        if (lbl) label = (lbl.innerText || '').trim();
                    }
                    items.push({
                        label: label.substring(0, 40),
                        on: isOn,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[4c] Toggles: {len(toggles)}")
        for t in toggles:
            state = "ON" if t['on'] else "OFF"
            print(f"  ({t['x']},{t['y']}) w={t['w']} '{t['label']}' [{state}] cls={t['cls'][:30]}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p150_img2img.png"))

        # ============================================================
        # 5. VIDEO EDITOR — Model options
        # ============================================================
        print(f"\n{'='*60}")
        print("5. VIDEO EDITOR — Model Options")
        print(f"{'='*60}")

        # Open Video Editor
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)
        page.mouse.click(40, 197)  # Toggle away
        page.wait_for_timeout(500)
        page.mouse.click(40, 490)  # Video Editor
        page.wait_for_timeout(2000)

        # Click model selector in Video Editor
        ve_selector = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var wrapper = panel.querySelector('.custom-selector-wrapper');
            if (wrapper) {
                var r = wrapper.getBoundingClientRect();
                wrapper.click();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
            return null;
        }""")
        print(f"[5] Model selector clicked: {ve_selector}")
        page.wait_for_timeout(2000)

        # Read model list
        ve_models = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (panel) {
                return {
                    text: panel.innerText.substring(0, 3000),
                    x: Math.round(panel.getBoundingClientRect().x),
                    y: Math.round(panel.getBoundingClientRect().y),
                    w: Math.round(panel.getBoundingClientRect().width),
                    h: Math.round(panel.getBoundingClientRect().height)
                };
            }
            return null;
        }""")
        if ve_models:
            print(f"[5] Selector panel: ({ve_models['x']},{ve_models['y']}) {ve_models['w']}x{ve_models['h']}")
            print(f"[5] Models:\n{ve_models['text'][:2000]}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p150_video_editor_models.png"))

        # Extract individual model items
        ve_items = page.evaluate("""() => {
            var items = [];
            var panel = document.querySelector('.selector-panel');
            if (!panel) return items;
            for (var el of panel.querySelectorAll('.select-item, [class*="model-item"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width > 0 && text.length > 2) {
                    items.push({
                        text: text.substring(0, 120),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        selected: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            return items;
        }""")
        print(f"\n[5b] Model items: {len(ve_items)}")
        for item in ve_items[:20]:
            sel = " [SELECTED]" if item['selected'] else ""
            name = item['text'].replace('\n', ' | ')[:80]
            print(f"  ({item['x']},{item['y']}) {item['w']}x{item['h']} '{name}'{sel}")

        # Close selector
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # 6. MOTION CONTROL — Model options
        # ============================================================
        print(f"\n{'='*60}")
        print("6. MOTION CONTROL — Model Options")
        print(f"{'='*60}")

        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)
        page.mouse.click(40, 197)
        page.wait_for_timeout(500)
        page.mouse.click(40, 551)  # Motion Control
        page.wait_for_timeout(2000)

        # Check for model selector
        mc_selector = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var wrapper = panel.querySelector('.custom-selector-wrapper');
            if (wrapper) {
                var r = wrapper.getBoundingClientRect();
                wrapper.click();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
            return null;
        }""")
        print(f"[6] Model selector: {mc_selector}")
        page.wait_for_timeout(2000)

        mc_models = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (panel) {
                return {
                    text: panel.innerText.substring(0, 3000),
                    w: Math.round(panel.getBoundingClientRect().width),
                    h: Math.round(panel.getBoundingClientRect().height)
                };
            }
            return null;
        }""")
        if mc_models:
            print(f"[6] Models: {mc_models['w']}x{mc_models['h']}")
            print(f"[6] Content:\n{mc_models['text'][:2000]}")
        else:
            print("[6] No selector panel — may have single model only")

        page.screenshot(path=os.path.expanduser("~/Downloads/p150_motion_models.png"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # 7. CREDITS DISPLAY — Exact format and location
        # ============================================================
        print(f"\n{'='*60}")
        print("7. CREDITS DISPLAY")
        print(f"{'='*60}")

        credits_info = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text.includes('Unlimited') || text.includes('credits') || text.match(/^[\\d.]+$/)) &&
                    text.length < 30 && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.y < 40 && r.x > 400 && r.width > 0) {
                        items.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width),
                            cls: (el.className || '').substring(0, 40),
                            tag: el.tagName
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"[7] Credit elements: {len(credits_info)}")
        for c in credits_info:
            print(f"  ({c['x']},{c['y']}) w={c['w']} <{c['tag']}> '{c['text']}' cls={c['cls'][:30]}")

        # ============================================================
        # 8. LAYERS PANEL — Structure and functionality
        # ============================================================
        print(f"\n{'='*60}")
        print("8. LAYERS PANEL")
        print(f"{'='*60}")

        # Close all panels first
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # Click Layers tab
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Layer')) { el.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        layers = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.layer-item, [class*="layer-item"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0) {
                    items.push({
                        text: text.substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            return items;
        }""")
        print(f"[8] Layers: {len(layers)}")
        for l in layers:
            print(f"  ({l['x']},{l['y']}) {l['w']}x{l['h']} '{l['text'][:50]}' cls={l['cls'][:40]}")

        # Get layer panel controls
        layer_controls = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x > 1000 && r.y > 80) {
                    var text = (el.innerText || el.title || '').trim();
                    items.push({
                        text: text.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 40),
                        title: (el.title || '').substring(0, 40)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[8b] Layer panel controls: {len(layer_controls)}")
        for c in layer_controls[:20]:
            title = f" title='{c['title']}'" if c['title'] else ""
            print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text'][:30]}' cls={c['cls'][:30]}{title}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p150_layers.png"))

        # Switch back to Results
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(500)

        # ============================================================
        # SUMMARY
        # ============================================================
        print("\n" + "=" * 70)
        print("PHASE 150 SUMMARY")
        print("=" * 70)
        print(f"  Top toolbar items: {len(toolbar)}")
        print(f"  Action bar items: {len(actionbar)}")
        print(f"  Style categories: {len(categories)}")
        print(f"  Total styles found: {len(all_styles)}")
        print(f"  Credits display elements: {len(credits_info)}")
        print(f"  Layers: {len(layers)}")
        print("  Check ~/Downloads/p150_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
