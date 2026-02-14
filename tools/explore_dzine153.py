#!/usr/bin/env python3
"""Phase 153: Product Background Tool — Full UI exploration.

Goals:
1. Find the Product Background tool (sidebar? Image Editor sub-tool? separate page?)
2. Document every UI element: inputs, sliders, buttons, upload areas, options
3. Test a generation if possible
4. Record selectors for automation

Prior findings (conflicting):
- dzine_playbook.md says: position (92, 877) in Image Editor as `subtool-item`
- dzine_ui_map.md says: NOT a sub-tool in Image Editor, accessed via BG Remove or web tool
- video_study_QIQ3QjgYes8.md says: 13th sidebar tool (newest, added recently)
- dzine_models_guide.md: has workflow docs for it

This script will try ALL approaches:
A. Check if it's a new sidebar tool (scroll down past the 12 known tools)
B. Open Image Editor and scroll to bottom
C. Check BG Remove action bar
D. Check the web tool page
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

SCREENSHOT_DIR = Path("/tmp/dzine_explore_153")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"
VIEWPORT = {"width": 1440, "height": 900}


def ss(page, name: str):
    """Take a screenshot and log it."""
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  [SS] {path}")


def close_popups(page):
    """Close promotional/tutorial popups."""
    for _ in range(5):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click(timeout=1000)
                    page.wait_for_timeout(400)
                    found = True
            except Exception:
                pass
        if not found:
            break


def close_panels(page):
    """Close any open sidebar panels."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close'))
            el.click();
    }""")
    page.wait_for_timeout(500)


def get_panel_info(page) -> dict:
    """Get info about any currently open panel."""
    return page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) p = document.querySelector('.panels.show');
        if (!p) return {open: false, text: ''};
        var r = p.getBoundingClientRect();
        return {
            open: true,
            text: p.innerText.substring(0, 3000),
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            cls: (typeof p.className === 'string') ? p.className.substring(0, 80) : ''
        };
    }""")


def map_all_elements_in_region(page, label, x_min, x_max, y_min, y_max):
    """Map all interactive elements within a region."""
    elements = page.evaluate(f"""() => {{
        var items = [];
        var allEls = document.querySelectorAll('button, input, textarea, select, [contenteditable], [role="button"], [role="slider"], .c-switch, label, a, [class*="upload"], [class*="drop"]');
        for (var el of allEls) {{
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 &&
                r.x >= {x_min} && r.x <= {x_max} &&
                r.y >= {y_min} && r.y <= {y_max}) {{
                var text = (el.innerText || el.value || el.placeholder || '').trim().substring(0, 80);
                var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
                items.push({{
                    tag: el.tagName,
                    text: text,
                    id: el.id || '',
                    cls: className.substring(0, 80),
                    type: el.type || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    disabled: el.disabled || false,
                    checked: el.checked || false,
                    placeholder: (el.placeholder || '').substring(0, 60),
                    role: el.getAttribute('role') || ''
                }});
            }}
        }}
        // Deduplicate by position
        var seen = new Set();
        return items.filter(i => {{
            var key = i.x + ',' + i.y + ',' + i.w;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }});
    }}""")
    print(f"\n  [{label}] Found {len(elements)} elements:")
    for e in elements:
        extra = ""
        if e['id']:
            extra += f" id={e['id']}"
        if e['disabled']:
            extra += " [DISABLED]"
        if e['checked']:
            extra += " [CHECKED]"
        if e['placeholder']:
            extra += f" ph='{e['placeholder']}'"
        if e['role']:
            extra += f" role={e['role']}"
        name = e['text'].replace('\n', ' | ')[:60]
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> cls='{e['cls'][:50]}' '{name}'{extra}")
    return elements


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running

    print("=" * 70)
    print("PHASE 153: Product Background Tool — Full UI Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P153] ERROR: Brave not running on port", DEFAULT_CDP_PORT)
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find or create Dzine canvas tab
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
            print(f"[P153] Using existing Dzine tab: {page.url}")
        else:
            page = context.new_page()
            print(f"[P153] Navigating to Dzine canvas...")
            page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)

        close_popups(page)
        page.wait_for_timeout(500)
        close_panels(page)
        page.wait_for_timeout(500)

        ss(page, "00_initial_state")

        # ================================================================
        # APPROACH A: Check sidebar for Product Background as a 13th tool
        # ================================================================
        print("\n" + "=" * 70)
        print("APPROACH A: Sidebar — scanning all icon positions")
        print("=" * 70)

        # Map all sidebar icons (x ~ 0-80, full height)
        sidebar_icons = page.evaluate("""() => {
            var items = [];
            var allEls = document.querySelectorAll('.sidebar-tool, [class*="sidebar"] button, [class*="sidebar"] a, [class*="side-bar"] *, [class*="tool-item"], [class*="menu-item"]');
            for (var el of allEls) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x < 80 && r.y > 50 && r.y < 900) {
                    var text = (el.innerText || el.title || el.getAttribute('aria-label') || '').trim();
                    var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
                    items.push({
                        text: text.substring(0, 50),
                        cls: className.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName
                    });
                }
            }
            // Deduplicate
            var seen = new Set();
            return items.filter(i => {
                var key = i.y + ',' + i.h;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);
        }""")
        print(f"[A] Sidebar elements: {len(sidebar_icons)}")
        for s in sidebar_icons:
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> cls='{s['cls'][:50]}' '{s['text']}'")

        # Also try broader search: any element at x < 80 that has tooltip or text
        sidebar_all = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.width > 20 && r.width < 80 && r.height > 20 && r.height < 80 &&
                    r.x < 80 && r.y > 50 && r.y < 900 && el.childElementCount <= 2) {
                    var text = (el.innerText || el.title || el.getAttribute('aria-label') || el.getAttribute('data-tooltip') || '').trim();
                    var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
                    if (className.length > 0 || text.length > 0) {
                        items.push({
                            text: text.substring(0, 50),
                            cls: className.substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName,
                            title: (el.title || '').substring(0, 40),
                            tooltip: (el.getAttribute('data-tooltip') || el.getAttribute('data-tip') || '').substring(0, 40)
                        });
                    }
                }
            }
            var seen = new Set();
            return items.filter(i => {
                var key = Math.round(i.y / 5) * 5;  // group by ~5px bands
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);
        }""")
        print(f"\n[A2] All sidebar-area elements (deduplicated by y-band): {len(sidebar_all)}")
        for s in sidebar_all:
            extra = ""
            if s['title']:
                extra += f" title='{s['title']}'"
            if s['tooltip']:
                extra += f" tip='{s['tooltip']}'"
            print(f"  y={s['y']} ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> cls='{s['cls'][:40]}' '{s['text'][:30]}'{extra}")

        # Check if sidebar is scrollable
        sidebar_scroll = page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="sidebar"], [class*="side-bar"], [class*="tool-bar"]')) {
                var r = el.getBoundingClientRect();
                if (r.x < 80 && r.height > 200) {
                    return {
                        cls: (typeof el.className === 'string') ? el.className.substring(0, 80) : '',
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        scrollable: el.scrollHeight > el.clientHeight + 10,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    };
                }
            }
            return null;
        }""")
        print(f"\n[A3] Sidebar scrollable container: {json.dumps(sidebar_scroll, indent=2)}")

        # If sidebar is scrollable, scroll down and check for more tools
        if sidebar_scroll and sidebar_scroll.get('scrollable'):
            print("[A4] Sidebar IS scrollable — scrolling down...")
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('[class*="sidebar"], [class*="side-bar"]')) {
                    if (el.scrollHeight > el.clientHeight + 10 && el.getBoundingClientRect().x < 80) {
                        el.scrollTop = el.scrollHeight;
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(1000)
            ss(page, "01_sidebar_scrolled")

            # Re-scan after scroll
            more_icons = page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 20 && r.width < 80 && r.height > 20 && r.height < 80 &&
                        r.x < 80 && r.y > 50 && r.y < 900 && el.childElementCount <= 2) {
                        var text = (el.innerText || el.title || '').trim();
                        var className = (typeof el.className === 'string') ? el.className : '';
                        if (className.length > 0 || text.length > 0) {
                            items.push({
                                text: text.substring(0, 50),
                                cls: className.substring(0, 60),
                                y: Math.round(r.y)
                            });
                        }
                    }
                }
                var seen = new Set();
                return items.filter(i => {
                    var key = Math.round(i.y / 5) * 5;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).sort((a, b) => a.y - b.y);
            }""")
            print(f"[A4] After scroll: {len(more_icons)} elements")
            for s in more_icons:
                print(f"  y={s['y']} cls='{s['cls'][:40]}' '{s['text'][:30]}'")

        # Try clicking each known sidebar position to identify tools
        # Known positions from dzine_browser.py SIDEBAR dict:
        known_positions = [
            (81, "upload"), (136, "assets"), (197, "txt2img"), (252, "img2img"),
            (306, "character"), (361, "ai_video"), (425, "lip_sync"),
            (490, "video_editor"), (550, "motion_control"), (627, "enhance_upscale"),
            (698, "image_editor"), (766, "instant_storyboard"),
        ]

        # Also try positions below 766 to find a 13th tool
        extra_positions = [(820, "unknown_13th"), (870, "unknown_14th")]

        print("\n[A5] Testing sidebar positions (below known tools)...")
        for y, label in extra_positions:
            close_panels(page)
            page.wait_for_timeout(300)
            # Click somewhere else first, then the target
            page.mouse.click(40, 197)
            page.wait_for_timeout(1000)
            page.mouse.click(40, y)
            page.wait_for_timeout(2000)
            panel = get_panel_info(page)
            if panel['open']:
                first_line = panel['text'].split('\n')[0][:60]
                print(f"  y={y} ({label}): PANEL OPEN -> '{first_line}'")
            else:
                print(f"  y={y} ({label}): no panel opened")

        # Hover over each sidebar position to get tooltip text
        print("\n[A6] Hovering sidebar icons for tooltips...")
        for y, label in known_positions + extra_positions:
            page.mouse.move(40, y)
            page.wait_for_timeout(800)
            tooltip = page.evaluate("""() => {
                // Look for any tooltip/popover that appeared
                for (var el of document.querySelectorAll('[class*="tooltip"], [class*="tip"], [role="tooltip"], .ant-tooltip, [class*="popover"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return {text: (el.innerText || '').trim().substring(0, 60), cls: (typeof el.className === 'string') ? el.className.substring(0, 50) : ''};
                    }
                }
                return null;
            }""")
            if tooltip:
                print(f"  y={y} ({label}): tooltip -> '{tooltip['text']}'")
            else:
                # Alternative: check for any new visible text near hover position
                near_text = page.evaluate(f"""() => {{
                    for (var el of document.querySelectorAll('*')) {{
                        var r = el.getBoundingClientRect();
                        if (r.x > 60 && r.x < 200 && Math.abs(r.y - {y}) < 30 &&
                            r.width > 30 && r.height < 40 && el.childElementCount === 0) {{
                            var text = (el.innerText || '').trim();
                            if (text.length > 1 && text.length < 40) return text;
                        }}
                    }}
                    return null;
                }}""")
                if near_text:
                    print(f"  y={y} ({label}): near text -> '{near_text}'")
                else:
                    print(f"  y={y} ({label}): no tooltip")

        ss(page, "02_sidebar_tooltips")

        # ================================================================
        # APPROACH B: Image Editor — scroll down to find Product Background
        # ================================================================
        print("\n" + "=" * 70)
        print("APPROACH B: Image Editor panel — scroll to find Product Background")
        print("=" * 70)

        close_panels(page)
        page.wait_for_timeout(500)

        # Open Image Editor (y=698)
        page.mouse.click(40, 197)  # Click something else first
        page.wait_for_timeout(1000)
        page.mouse.click(40, 698)  # Image Editor
        page.wait_for_timeout(2500)

        ss(page, "03_image_editor_open")
        panel = get_panel_info(page)
        if panel['open']:
            print(f"[B] Image Editor panel: {panel['w']}x{panel['h']} at ({panel['x']},{panel['y']})")
            print(f"[B] Panel text (first 500 chars):\n{panel['text'][:500]}")
        else:
            print("[B] WARNING: Image Editor panel did not open")

        # Map all sub-tools in Image Editor
        subtools = page.evaluate("""() => {
            var items = [];
            var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
            if (!panel) return items;
            for (var el of panel.querySelectorAll('.subtool-item, .collapse-option, [class*="subtool"], [class*="sub-tool"], button')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 30 && r.height > 20 && text.length > 0 && text.length < 60) {
                    var className = (typeof el.className === 'string') ? el.className : '';
                    items.push({
                        text: text.substring(0, 60),
                        cls: className.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName
                    });
                }
            }
            return items.sort((a, b) => a.y - b.y);
        }""")
        print(f"\n[B2] Image Editor sub-tools: {len(subtools)}")
        for s in subtools:
            name = s['text'].replace('\n', ' | ')[:50]
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> cls='{s['cls'][:40]}' '{name}'")

        # Check if the panel container is scrollable
        panel_scroll = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
            if (!panel) return null;
            // Find scrollable child
            for (var el of panel.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 20 && el.clientHeight > 100) {
                    var r = el.getBoundingClientRect();
                    var className = (typeof el.className === 'string') ? el.className : '';
                    return {
                        cls: className.substring(0, 80),
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        scrollTop: el.scrollTop,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    };
                }
            }
            return null;
        }""")
        print(f"\n[B3] Panel scrollable container: {json.dumps(panel_scroll, indent=2)}")

        if panel_scroll and panel_scroll['scrollHeight'] > panel_scroll['clientHeight']:
            print("[B4] Panel IS scrollable — scrolling to bottom...")
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
                if (!panel) return;
                for (var el of panel.querySelectorAll('*')) {
                    if (el.scrollHeight > el.clientHeight + 20 && el.clientHeight > 100) {
                        el.scrollTop = el.scrollHeight;
                        return;
                    }
                }
            }""")
            page.wait_for_timeout(1000)
            ss(page, "04_image_editor_scrolled")

            # Re-scan after scroll
            subtools_bottom = page.evaluate("""() => {
                var items = [];
                var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
                if (!panel) return items;
                for (var el of panel.querySelectorAll('.subtool-item, .collapse-option, [class*="subtool"], [class*="background"], button')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.width > 30 && r.height > 20 && text.length > 0 && text.length < 60) {
                        var className = (typeof el.className === 'string') ? el.className : '';
                        items.push({
                            text: text.substring(0, 60),
                            cls: className.substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName
                        });
                    }
                }
                return items.sort((a, b) => a.y - b.y);
            }""")
            print(f"[B4] After scroll - elements: {len(subtools_bottom)}")
            for s in subtools_bottom:
                name = s['text'].replace('\n', ' | ')[:50]
                highlight = " <<<" if "background" in name.lower() or "product" in name.lower() else ""
                print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> cls='{s['cls'][:40]}' '{name}'{highlight}")

        # Specific search for "Background" or "Product Background" text anywhere in panel
        bg_search = page.evaluate("""() => {
            var results = [];
            var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
            if (!panel) panel = document;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text.toLowerCase().includes('product background') ||
                     (text === 'Background' && el.childElementCount === 0)) &&
                    el.getBoundingClientRect().width > 0) {
                    var r = el.getBoundingClientRect();
                    var className = (typeof el.className === 'string') ? el.className : '';
                    results.push({
                        text: text.substring(0, 80),
                        cls: className.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        visible: r.height > 0 && r.width > 0
                    });
                }
            }
            return results;
        }""")
        print(f"\n[B5] 'Background' / 'Product Background' text search: {len(bg_search)} matches")
        for b in bg_search:
            print(f"  ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> cls='{b['cls'][:40]}' '{b['text'][:60]}'")

        # If found, click it!
        clicked_bg = False
        if bg_search:
            for b in bg_search:
                if b['visible'] and b['w'] > 30:
                    print(f"\n[B6] Clicking Product Background at ({b['x']},{b['y']})...")
                    page.mouse.click(b['x'] + b['w'] // 2, b['y'] + b['h'] // 2)
                    page.wait_for_timeout(3000)
                    ss(page, "05_product_bg_clicked")

                    # Map the resulting panel
                    new_panel = get_panel_info(page)
                    if new_panel['open']:
                        print(f"[B6] Panel opened: {new_panel['w']}x{new_panel['h']}")
                        print(f"[B6] Panel text:\n{new_panel['text'][:1000]}")

                        # Map ALL interactive elements in the panel
                        map_all_elements_in_region(page, "Product BG Panel", 60, 400, 50, 900)
                        clicked_bg = True
                    break

        # ================================================================
        # APPROACH C: BG Remove in top action bar
        # ================================================================
        print("\n" + "=" * 70)
        print("APPROACH C: Top action bar — BG Remove")
        print("=" * 70)

        close_panels(page)
        page.wait_for_timeout(500)

        # First, select a layer on canvas (action bar tools often need this)
        page.mouse.click(720, 450)
        page.wait_for_timeout(1000)

        # Look for BG Remove button in the action bar
        bg_remove_btn = page.evaluate("""() => {
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var text = (el.innerText || el.title || '').trim();
                if (text.toLowerCase().includes('bg remove') || text.toLowerCase().includes('background') ||
                    text.toLowerCase().includes('remove bg') || text.toLowerCase().includes('bg ')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        var className = (typeof el.className === 'string') ? el.className : '';
                        return {
                            text: text.substring(0, 60),
                            cls: className.substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)
                        };
                    }
                }
            }
            return null;
        }""")
        print(f"[C] BG Remove button: {json.dumps(bg_remove_btn)}")

        if bg_remove_btn:
            print(f"[C2] Clicking BG Remove at ({bg_remove_btn['x']},{bg_remove_btn['y']})...")
            page.mouse.click(bg_remove_btn['x'] + bg_remove_btn['w'] // 2,
                             bg_remove_btn['y'] + bg_remove_btn['h'] // 2)
            page.wait_for_timeout(3000)
            ss(page, "06_bg_remove_clicked")

            # Check what opened
            panel = get_panel_info(page)
            if panel['open']:
                print(f"[C2] Panel: {panel['text'][:500]}")

        # Also map the full action bar for reference
        action_bar = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var r = el.getBoundingClientRect();
                if (r.y > 50 && r.y < 120 && r.height > 0 && r.height < 50 && r.x > 80 && r.width > 0) {
                    var text = (el.innerText || el.title || '').trim();
                    var className = (typeof el.className === 'string') ? el.className : '';
                    items.push({
                        text: text.substring(0, 40),
                        cls: className.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width)
                    });
                }
            }
            return items.sort((a, b) => a.x - b.x);
        }""")
        print(f"\n[C3] Top action bar buttons: {len(action_bar)}")
        for b in action_bar:
            print(f"  x={b['x']} w={b['w']} cls='{b['cls'][:40]}' '{b['text']}'")

        ss(page, "07_action_bar")

        # ================================================================
        # APPROACH D: Search entire page DOM for "Product Background"
        # ================================================================
        print("\n" + "=" * 70)
        print("APPROACH D: Full DOM search for Product Background")
        print("=" * 70)

        full_search = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || el.title || el.getAttribute('aria-label') || '').trim();
                if (text.toLowerCase() === 'product background' ||
                    text.toLowerCase() === 'product bg' ||
                    (el.className && typeof el.className === 'string' &&
                     (el.className.toLowerCase().includes('product-bg') ||
                      el.className.toLowerCase().includes('product-background')))) {
                    var r = el.getBoundingClientRect();
                    var className = (typeof el.className === 'string') ? el.className : '';
                    results.push({
                        text: text.substring(0, 80),
                        cls: className.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        visible: r.width > 0 && r.height > 0,
                        parent_cls: (el.parentElement && typeof el.parentElement.className === 'string') ? el.parentElement.className.substring(0, 60) : ''
                    });
                }
            }
            return results;
        }""")
        print(f"[D] Exact 'Product Background' matches: {len(full_search)}")
        for f in full_search:
            vis = "VISIBLE" if f['visible'] else "hidden"
            print(f"  ({f['x']},{f['y']}) {f['w']}x{f['h']} <{f['tag']}> [{vis}] cls='{f['cls'][:40]}' parent='{f['parent_cls'][:40]}' '{f['text'][:60]}'")

        # ================================================================
        # APPROACH E: Navigate to the web tool page
        # ================================================================
        print("\n" + "=" * 70)
        print("APPROACH E: Web tool page — dzine.ai/tools/ai-product-background-generator/")
        print("=" * 70)

        # Open in a new tab
        web_tool_page = context.new_page()
        web_tool_page.set_viewport_size(VIEWPORT)
        try:
            web_tool_page.goto("https://www.dzine.ai/tools/ai-product-background-generator/",
                               wait_until="domcontentloaded", timeout=30000)
            web_tool_page.wait_for_timeout(5000)
            close_popups_on = web_tool_page
            for text_btn in ["Not now", "Close", "Got it", "Skip"]:
                try:
                    btn = close_popups_on.locator(f'button:has-text("{text_btn}")')
                    if btn.count() > 0:
                        btn.first.click(timeout=1000)
                        web_tool_page.wait_for_timeout(400)
                except Exception:
                    pass

            ss_path = SCREENSHOT_DIR / "08_web_tool_page.png"
            web_tool_page.screenshot(path=str(ss_path))
            print(f"  [SS] {ss_path}")

            # Check if it redirected
            print(f"[E] URL after load: {web_tool_page.url}")

            # Map the page
            page_content = web_tool_page.evaluate("""() => {
                return {
                    title: document.title,
                    h1: document.querySelector('h1') ? document.querySelector('h1').innerText : '',
                    bodyText: document.body.innerText.substring(0, 2000)
                };
            }""")
            print(f"[E] Title: {page_content['title']}")
            print(f"[E] H1: {page_content['h1']}")
            print(f"[E] Body text (first 500):\n{page_content['bodyText'][:500]}")

            # Find upload areas, buttons, interactive elements
            web_elements = web_tool_page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('button, input, textarea, [contenteditable], [role="button"], [class*="upload"], [class*="drop"], [class*="generate"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        var text = (el.innerText || el.value || el.placeholder || '').trim();
                        var className = (typeof el.className === 'string') ? el.className : '';
                        items.push({
                            tag: el.tagName,
                            text: text.substring(0, 80),
                            cls: className.substring(0, 80),
                            type: el.type || '',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            id: el.id || '',
                            placeholder: (el.placeholder || '').substring(0, 60)
                        });
                    }
                }
                return items.sort((a, b) => a.y - b.y);
            }""")
            print(f"\n[E2] Interactive elements on web tool page: {len(web_elements)}")
            for e in web_elements[:40]:
                extra = ""
                if e['id']:
                    extra += f" id={e['id']}"
                if e['placeholder']:
                    extra += f" ph='{e['placeholder']}'"
                name = e['text'].replace('\n', ' | ')[:50]
                print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> cls='{e['cls'][:40]}' '{name}'{extra}")

            # Check if there are template/scene categories
            templates = web_tool_page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('[class*="template"], [class*="scene"], [class*="category"], [class*="preset"], img[class*="bg"], [class*="thumb"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 30 && r.height > 30) {
                        var text = (el.alt || el.title || el.innerText || '').trim();
                        var className = (typeof el.className === 'string') ? el.className : '';
                        items.push({
                            tag: el.tagName,
                            text: text.substring(0, 60),
                            cls: className.substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            src: (el.src || '').substring(0, 100)
                        });
                    }
                }
                return items.sort((a, b) => a.y - b.y);
            }""")
            print(f"\n[E3] Template/scene elements: {len(templates)}")
            for t in templates[:20]:
                print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> cls='{t['cls'][:40]}' '{t['text'][:40]}'")
                if t.get('src'):
                    print(f"    src: {t['src'][:80]}")

            # Scroll down to see more content
            web_tool_page.evaluate("window.scrollTo(0, 800)")
            page.wait_for_timeout(1500)
            ss_path2 = SCREENSHOT_DIR / "09_web_tool_scrolled.png"
            web_tool_page.screenshot(path=str(ss_path2))
            print(f"  [SS] {ss_path2}")

            # Check for file input (hidden upload)
            file_inputs = web_tool_page.evaluate("""() => {
                var inputs = [];
                for (var el of document.querySelectorAll('input[type="file"]')) {
                    inputs.push({
                        accept: el.accept || '',
                        multiple: el.multiple,
                        cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                        id: el.id || '',
                        name: el.name || ''
                    });
                }
                return inputs;
            }""")
            print(f"\n[E4] File inputs: {len(file_inputs)}")
            for fi in file_inputs:
                print(f"  accept='{fi['accept']}' multiple={fi['multiple']} id='{fi['id']}' name='{fi['name']}'")

        except Exception as exc:
            print(f"[E] ERROR loading web tool page: {exc}")
        finally:
            try:
                web_tool_page.close()
            except Exception:
                pass

        # ================================================================
        # APPROACH F: Check aiTools hub for Product Background link
        # ================================================================
        print("\n" + "=" * 70)
        print("APPROACH F: AI Tools hub page")
        print("=" * 70)

        tools_page = context.new_page()
        tools_page.set_viewport_size(VIEWPORT)
        try:
            tools_page.goto("https://www.dzine.ai/aiTools", wait_until="domcontentloaded", timeout=30000)
            tools_page.wait_for_timeout(5000)
            for text_btn in ["Not now", "Close", "Got it", "Skip"]:
                try:
                    btn = tools_page.locator(f'button:has-text("{text_btn}")')
                    if btn.count() > 0:
                        btn.first.click(timeout=1000)
                        tools_page.wait_for_timeout(400)
                except Exception:
                    pass

            ss_path = SCREENSHOT_DIR / "10_ai_tools_hub.png"
            tools_page.screenshot(path=str(ss_path))
            print(f"  [SS] {ss_path}")
            print(f"[F] URL: {tools_page.url}")

            # Find all tool cards/links
            tool_cards = tools_page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('a, button, [class*="tool-card"], [class*="tool-item"]')) {
                    var text = (el.innerText || el.title || '').trim();
                    if (text.toLowerCase().includes('background') || text.toLowerCase().includes('product') ||
                        text.toLowerCase().includes('remove') || text.toLowerCase().includes('replace')) {
                        var r = el.getBoundingClientRect();
                        var className = (typeof el.className === 'string') ? el.className : '';
                        items.push({
                            tag: el.tagName,
                            text: text.substring(0, 80),
                            cls: className.substring(0, 60),
                            href: el.href || '',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)
                        });
                    }
                }
                return items;
            }""")
            print(f"[F2] Background/Product related tools: {len(tool_cards)}")
            for t in tool_cards:
                name = t['text'].replace('\n', ' | ')[:60]
                print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> '{name}' href={t.get('href', '')[:80]}")

            # Also dump all tool names on the page
            all_tools = tools_page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('h3, h4, [class*="title"], [class*="name"]')) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 40 && el.childElementCount === 0) {
                        items.push(text);
                    }
                }
                return [...new Set(items)];
            }""")
            print(f"\n[F3] All tool names on page: {len(all_tools)}")
            for name in all_tools:
                highlight = " <<<" if "background" in name.lower() or "product" in name.lower() else ""
                print(f"  {name}{highlight}")

            # Scroll down for more
            tools_page.evaluate("window.scrollTo(0, 1500)")
            tools_page.wait_for_timeout(1500)
            ss_path = SCREENSHOT_DIR / "11_ai_tools_scrolled.png"
            tools_page.screenshot(path=str(ss_path))
            print(f"  [SS] {ss_path}")

        except Exception as exc:
            print(f"[F] ERROR: {exc}")
        finally:
            try:
                tools_page.close()
            except Exception:
                pass

        # ================================================================
        # Go back to canvas and try one more thing: right-click canvas
        # ================================================================
        print("\n" + "=" * 70)
        print("APPROACH G: Canvas context menu / right-click")
        print("=" * 70)

        page.bring_to_front()
        page.wait_for_timeout(500)
        close_popups(page)
        close_panels(page)
        page.wait_for_timeout(500)

        # Select a layer first
        page.mouse.click(720, 450)
        page.wait_for_timeout(500)

        # Right-click
        page.mouse.click(720, 450, button="right")
        page.wait_for_timeout(2000)
        ss(page, "12_context_menu")

        # Read context menu items
        ctx_menu = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('[class*="context-menu"] *, [class*="contextmenu"] *, [role="menu"] *, [role="menuitem"]')) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 40 && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        items.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
                    }
                }
            }
            return [...new Map(items.map(i => [i.text, i])).values()];
        }""")
        print(f"[G] Context menu items: {len(ctx_menu)}")
        for c in ctx_menu:
            highlight = " <<<" if "background" in c['text'].lower() else ""
            print(f"  ({c['x']},{c['y']}) '{c['text']}'{highlight}")

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ================================================================
        # SUMMARY
        # ================================================================
        print("\n" + "=" * 70)
        print("PHASE 153 SUMMARY")
        print("=" * 70)
        print(f"Screenshots saved to: {SCREENSHOT_DIR}")
        print(f"Total screenshots: {len(list(SCREENSHOT_DIR.glob('*.png')))}")

        # List all screenshots
        for f in sorted(SCREENSHOT_DIR.glob("*.png")):
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.0f} KB)")

    except Exception as exc:
        print(f"\n[P153] FATAL ERROR: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            pw.stop()
        except Exception:
            pass


def main_part2():
    """Part 2: Click the actual Background subtool and map its panel in detail."""
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running

    print("=" * 70)
    print("PHASE 153 PART 2: Product Background — Deep Panel Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P153b] ERROR: Brave not running")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P153b] No Dzine canvas tab found")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)
        close_popups(page)
        close_panels(page)
        page.wait_for_timeout(500)

        # ================================================================
        # STEP 1: Open Image Editor sidebar
        # ================================================================
        print("\n[STEP 1] Opening Image Editor sidebar...")

        # Click another tool first, then Image Editor
        page.mouse.click(40, 197)  # Txt2Img
        page.wait_for_timeout(1000)
        page.mouse.click(40, 674)  # Image Editor (updated y from scan)
        page.wait_for_timeout(2500)

        panel = get_panel_info(page)
        if not panel['open'] or 'Image Editor' not in panel['text']:
            # Try the known position
            page.mouse.click(40, 698)
            page.wait_for_timeout(2500)
            panel = get_panel_info(page)

        print(f"[STEP 1] Panel open: {panel['open']}")
        if panel['open']:
            print(f"[STEP 1] First line: {panel['text'].split(chr(10))[0]}")

        ss(page, "p2_01_image_editor")

        # ================================================================
        # STEP 2: Scroll to bottom and click Background subtool
        # ================================================================
        print("\n[STEP 2] Scrolling to Product Background and clicking...")

        # Scroll the panel to reveal Product Background
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
            if (!panel) return false;
            for (var el of panel.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 20 && el.clientHeight > 100) {
                    el.scrollTop = el.scrollHeight;
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Now click the "Background" subtool-item
        # It should be a div.subtool-item with text "Background"
        clicked = page.evaluate("""() => {
            var items = document.querySelectorAll('.subtool-item');
            for (var item of items) {
                var text = (item.innerText || '').trim();
                if (text.includes('Background')) {
                    var r = item.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        item.click();
                        return {text: text, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                    }
                }
            }
            // Fallback: find and click by class
            var category = document.querySelector('.subtool-category:last-child');
            if (category) {
                var btn = category.querySelector('.subtool-item');
                if (btn) {
                    btn.click();
                    var r = btn.getBoundingClientRect();
                    return {text: (btn.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y), fallback: true};
                }
            }
            return null;
        }""")
        print(f"[STEP 2] Clicked Background: {json.dumps(clicked)}")
        page.wait_for_timeout(3000)

        ss(page, "p2_02_background_clicked")

        # ================================================================
        # STEP 3: Map the Product Background panel
        # ================================================================
        print("\n[STEP 3] Mapping Product Background panel...")

        # Check what panel opened
        new_panel = page.evaluate("""() => {
            // Check for the hidden panel that has float-pro-img class
            var proImg = document.querySelector('.c-gen-config.float-pro-img');
            if (proImg) {
                var r = proImg.getBoundingClientRect();
                var vis = window.getComputedStyle(proImg);
                return {
                    type: 'float-pro-img',
                    text: proImg.innerText.substring(0, 3000),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    display: vis.display,
                    visibility: vis.visibility,
                    opacity: vis.opacity,
                    cls: (typeof proImg.className === 'string') ? proImg.className : ''
                };
            }
            // Check for any gen-config panel that's shown
            var shown = document.querySelector('.c-gen-config.show');
            if (shown) {
                var r = shown.getBoundingClientRect();
                return {
                    type: 'show-panel',
                    text: shown.innerText.substring(0, 3000),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (typeof shown.className === 'string') ? shown.className : ''
                };
            }
            return null;
        }""")
        print(f"[STEP 3] Panel type: {new_panel['type'] if new_panel else 'NONE'}")
        if new_panel:
            print(f"[STEP 3] Panel class: {new_panel.get('cls', '')[:80]}")
            print(f"[STEP 3] Size: {new_panel.get('w', 0)}x{new_panel.get('h', 0)} at ({new_panel.get('x', 0)},{new_panel.get('y', 0)})")
            if 'display' in new_panel:
                print(f"[STEP 3] display={new_panel['display']} visibility={new_panel['visibility']} opacity={new_panel['opacity']}")
            print(f"[STEP 3] Text:\n{new_panel['text'][:1500]}")

        # Check ALL c-gen-config panels (visible or not)
        all_panels = page.evaluate("""() => {
            var panels = [];
            for (var el of document.querySelectorAll('.c-gen-config')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                var className = (typeof el.className === 'string') ? el.className : '';
                panels.push({
                    cls: className.substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    display: s.display,
                    opacity: s.opacity,
                    firstLine: (el.innerText || '').split('\\n')[0].substring(0, 60),
                    hasShow: className.includes('show'),
                    hasFloatProImg: className.includes('float-pro-img')
                });
            }
            return panels;
        }""")
        print(f"\n[STEP 3b] All c-gen-config panels: {len(all_panels)}")
        for p in all_panels:
            vis = "SHOW" if p['hasShow'] else "hidden"
            pro = " [FLOAT-PRO-IMG]" if p['hasFloatProImg'] else ""
            print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} [{vis}] display={p['display']} opacity={p['opacity']} '{p['firstLine']}'{pro}")

        # ================================================================
        # STEP 4: If panel has float-pro-img, try to make it visible
        # ================================================================
        print("\n[STEP 4] Trying to activate Product Background panel...")

        # The float-pro-img panel might need a specific trigger
        # Try clicking the Background item directly with JS click
        activated = page.evaluate("""() => {
            // Method 1: Click via the subtool-item image/thumbnail
            var items = document.querySelectorAll('.subtool-item');
            for (var item of items) {
                var text = (item.innerText || '').trim();
                if (text.includes('Background')) {
                    // Try clicking the image inside
                    var img = item.querySelector('img, .img, .icon');
                    if (img) img.click();
                    else item.click();
                    break;
                }
            }

            // Wait and check
            var proImg = document.querySelector('.c-gen-config.float-pro-img');
            if (proImg) {
                return {
                    cls: (typeof proImg.className === 'string') ? proImg.className : '',
                    display: window.getComputedStyle(proImg).display,
                    visibility: window.getComputedStyle(proImg).visibility,
                    opacity: window.getComputedStyle(proImg).opacity
                };
            }
            return null;
        }""")
        print(f"[STEP 4] After click: {json.dumps(activated)}")
        page.wait_for_timeout(2000)

        # Try forcing the panel visible
        page.evaluate("""() => {
            var proImg = document.querySelector('.c-gen-config.float-pro-img');
            if (proImg) {
                // Add 'show' class to make it visible
                proImg.classList.add('show');
                proImg.style.display = '';
                proImg.style.visibility = 'visible';
                proImg.style.opacity = '1';
                return true;
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        ss(page, "p2_03_product_bg_panel_forced")

        # Now map all elements in the Product Background panel
        pb_elements = page.evaluate("""() => {
            var proImg = document.querySelector('.c-gen-config.float-pro-img');
            if (!proImg) return [];
            var items = [];
            for (var el of proImg.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || el.value || el.placeholder || '').trim();
                var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
                if (r.width > 0 && r.height > 0 && (
                    el.tagName === 'BUTTON' || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ||
                    el.tagName === 'SELECT' || el.tagName === 'H5' || el.tagName === 'LABEL' ||
                    el.tagName === 'DIV' && (className.includes('upload') || className.includes('drop') ||
                        className.includes('switch') || className.includes('slider') ||
                        className.includes('option') || className.includes('prompt') ||
                        className.includes('template') || className.includes('scene')) ||
                    el.tagName === 'SPAN' && text.length > 0 && text.length < 40 && el.childElementCount === 0
                )) {
                    items.push({
                        tag: el.tagName,
                        text: text.substring(0, 80),
                        cls: className.substring(0, 80),
                        id: el.id || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        type: el.type || '',
                        placeholder: (el.placeholder || '').substring(0, 60),
                        disabled: el.disabled || false,
                        contentEditable: el.contentEditable === 'true'
                    });
                }
            }
            // Sort by y position
            items.sort((a, b) => a.y - b.y || a.x - b.x);
            // Deduplicate by position
            var seen = new Set();
            return items.filter(i => {
                var key = i.x + ',' + i.y + ',' + i.tag;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }""")
        print(f"\n[STEP 4b] Product Background panel elements: {len(pb_elements)}")
        for e in pb_elements:
            extra = ""
            if e['id']:
                extra += f" id={e['id']}"
            if e['disabled']:
                extra += " [DISABLED]"
            if e['placeholder']:
                extra += f" ph='{e['placeholder']}'"
            if e['contentEditable']:
                extra += " [EDITABLE]"
            name = e['text'].replace('\n', ' | ')[:50]
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> cls='{e['cls'][:50]}' '{name}'{extra}")

        # Get the full HTML structure of the panel for analysis
        panel_html = page.evaluate("""() => {
            var proImg = document.querySelector('.c-gen-config.float-pro-img');
            if (!proImg) return '';
            // Get simplified structure
            function mapEl(el, depth) {
                if (depth > 4) return '';
                var className = (typeof el.className === 'string') ? el.className : '';
                var text = el.childElementCount === 0 ? (el.innerText || '').trim().substring(0, 40) : '';
                var r = el.getBoundingClientRect();
                var indent = '  '.repeat(depth);
                var line = indent + '<' + el.tagName + ' cls="' + className.substring(0, 50) + '"';
                if (el.id) line += ' id="' + el.id + '"';
                if (text) line += ' text="' + text + '"';
                if (r.width > 0) line += ' pos="(' + Math.round(r.x) + ',' + Math.round(r.y) + ') ' + Math.round(r.width) + 'x' + Math.round(r.height) + '"';
                line += '>';
                var result = line + '\\n';
                for (var child of el.children) {
                    if (child.getBoundingClientRect().width > 0 || child.tagName === 'INPUT') {
                        result += mapEl(child, depth + 1);
                    }
                }
                return result;
            }
            return mapEl(proImg, 0);
        }""")
        print(f"\n[STEP 4c] Panel DOM structure:")
        print(pb_elements and panel_html[:3000] or "(empty)")

        # ================================================================
        # STEP 5: Check the panel text for prompt areas, templates, etc.
        # ================================================================
        print("\n[STEP 5] Analyzing panel content for automation targets...")

        panel_full_text = page.evaluate("""() => {
            var proImg = document.querySelector('.c-gen-config.float-pro-img.show');
            if (!proImg) {
                proImg = document.querySelector('.c-gen-config.float-pro-img');
            }
            if (proImg) return proImg.innerText;
            return 'NOT FOUND';
        }""")
        print(f"[STEP 5] Full panel text:\n{panel_full_text[:2000]}")

        # Look specifically for: upload area, prompt input, templates/scenes, generate button
        key_elements = page.evaluate("""() => {
            var proImg = document.querySelector('.c-gen-config.float-pro-img');
            if (!proImg) return {};
            return {
                upload: (() => {
                    var el = proImg.querySelector('[class*="upload"], [class*="drop"], .c-upload, input[type="file"]');
                    if (el) {
                        var r = el.getBoundingClientRect();
                        return {cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: (el.innerText || '').substring(0, 60)};
                    }
                    return null;
                })(),
                prompt: (() => {
                    var el = proImg.querySelector('textarea, [contenteditable="true"], .prompt-content, input[type="text"]');
                    if (el) {
                        var r = el.getBoundingClientRect();
                        return {tag: el.tagName, cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), placeholder: (el.placeholder || el.getAttribute('data-placeholder') || '').substring(0, 60)};
                    }
                    return null;
                })(),
                generateBtn: (() => {
                    var el = proImg.querySelector('button.generative, button.generate, [class*="generate"], button.consume-tip');
                    if (el) {
                        var r = el.getBoundingClientRect();
                        return {text: (el.innerText || '').trim(), cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), disabled: el.disabled};
                    }
                    return null;
                })(),
                templates: (() => {
                    var items = [];
                    for (var el of proImg.querySelectorAll('[class*="template"], [class*="scene"], [class*="preset"], [class*="category"]')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 30) {
                            items.push({cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '', text: (el.innerText || '').substring(0, 60), w: Math.round(r.width), h: Math.round(r.height)});
                        }
                    }
                    return items;
                })(),
                fileInputs: (() => {
                    var items = [];
                    for (var el of proImg.querySelectorAll('input[type="file"]')) {
                        items.push({accept: el.accept, name: el.name || '', id: el.id || '', multiple: el.multiple});
                    }
                    return items;
                })(),
                images: (() => {
                    var items = [];
                    for (var el of proImg.querySelectorAll('img')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 20) {
                            items.push({src: (el.src || '').substring(0, 100), alt: el.alt || '', w: Math.round(r.width), h: Math.round(r.height)});
                        }
                    }
                    return items;
                })()
            };
        }""")
        print(f"\n[STEP 5b] Key automation elements:")
        print(f"  Upload area: {json.dumps(key_elements.get('upload'))}")
        print(f"  Prompt input: {json.dumps(key_elements.get('prompt'))}")
        print(f"  Generate button: {json.dumps(key_elements.get('generateBtn'))}")
        print(f"  Templates: {json.dumps(key_elements.get('templates'), indent=2)}")
        print(f"  File inputs: {json.dumps(key_elements.get('fileInputs'))}")
        print(f"  Images: {json.dumps(key_elements.get('images'), indent=2)}")

        ss(page, "p2_04_product_bg_panel_mapped")

        # ================================================================
        # STEP 6: Try clicking "Background" via position from Image Editor
        # ================================================================
        print("\n[STEP 6] Alternative: click Background at known position...")

        # First reopen Image Editor
        close_panels(page)
        page.wait_for_timeout(500)
        page.mouse.click(40, 197)
        page.wait_for_timeout(1000)
        page.mouse.click(40, 674)
        page.wait_for_timeout(2500)

        # Scroll to bottom
        page.evaluate("""() => {
            var el = document.querySelector('.subtools');
            if (el) { el.scrollTop = el.scrollHeight; return true; }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Get the exact position of the Background subtool after scroll
        bg_pos = page.evaluate("""() => {
            var items = document.querySelectorAll('.subtool-item');
            for (var item of items) {
                var text = (item.innerText || '').trim();
                if (text.includes('Background')) {
                    var r = item.getBoundingClientRect();
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")
        print(f"[STEP 6] Background position: {json.dumps(bg_pos)}")

        if bg_pos:
            # Click directly at the center of the Background item
            page.mouse.click(bg_pos['cx'], bg_pos['cy'])
            page.wait_for_timeout(3000)
            ss(page, "p2_05_background_direct_click")

            # Check what happened
            after_click = page.evaluate("""() => {
                var results = {};
                // Check all c-gen-config panels
                for (var el of document.querySelectorAll('.c-gen-config')) {
                    var s = window.getComputedStyle(el);
                    var className = (typeof el.className === 'string') ? el.className : '';
                    if (s.display !== 'none' && s.opacity !== '0' && s.visibility !== 'hidden') {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0) {
                            results[className.substring(0, 60)] = {
                                text: (el.innerText || '').substring(0, 1000),
                                w: Math.round(r.width), h: Math.round(r.height),
                                x: Math.round(r.x), y: Math.round(r.y)
                            };
                        }
                    }
                }
                return results;
            }""")
            print(f"[STEP 6] Visible panels after click: {len(after_click)}")
            for cls, info in after_click.items():
                print(f"  '{cls[:60]}': {info['w']}x{info['h']} at ({info['x']},{info['y']})")
                print(f"    Text: {info['text'][:300]}")

        # ================================================================
        # STEP 7: Try to find Product Background via the "select a layer" flow
        # ================================================================
        print("\n[STEP 7] Selecting a canvas layer first, then trying Background...")

        close_panels(page)
        page.wait_for_timeout(500)

        # Click on the ring image on canvas to select a layer
        page.mouse.click(500, 400)
        page.wait_for_timeout(1000)

        # Now open Image Editor and try Background
        page.mouse.click(40, 674)
        page.wait_for_timeout(2500)

        # Scroll down
        page.evaluate("""() => {
            var el = document.querySelector('.subtools');
            if (el) { el.scrollTop = el.scrollHeight; }
        }""")
        page.wait_for_timeout(1000)

        ss(page, "p2_06_with_layer_selected")

        # Click Background
        bg_pos2 = page.evaluate("""() => {
            var items = document.querySelectorAll('.subtool-item');
            for (var item of items) {
                var text = (item.innerText || '').trim();
                if (text.includes('Background')) {
                    var r = item.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && r.y > 0) {
                        item.click();
                        return {clicked: true, x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            return {clicked: false};
        }""")
        print(f"[STEP 7] Background click: {json.dumps(bg_pos2)}")
        page.wait_for_timeout(3000)

        ss(page, "p2_07_background_with_layer")

        # Comprehensive check of what panel is showing
        final_state = page.evaluate("""() => {
            var results = {panels: [], overlays: [], genConfig: []};

            // Check all visible panels
            for (var el of document.querySelectorAll('.c-gen-config')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                var className = (typeof el.className === 'string') ? el.className : '';
                results.genConfig.push({
                    cls: className.substring(0, 80),
                    visible: r.width > 0 && s.display !== 'none' && s.opacity !== '0',
                    w: Math.round(r.width), h: Math.round(r.height),
                    x: Math.round(r.x), y: Math.round(r.y),
                    text: (el.innerText || '').substring(0, 500),
                    display: s.display, opacity: s.opacity, visibility: s.visibility,
                    zIndex: s.zIndex
                });
            }

            // Check for floating overlays
            for (var el of document.querySelectorAll('[class*="float"], [class*="overlay"], [class*="modal"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 100) {
                    var className = (typeof el.className === 'string') ? el.className : '';
                    results.overlays.push({
                        cls: className.substring(0, 60),
                        text: (el.innerText || '').substring(0, 200),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }

            return results;
        }""")
        print(f"\n[STEP 7b] Final state:")
        print(f"  gen-config panels: {len(final_state['genConfig'])}")
        for p in final_state['genConfig']:
            vis = "VISIBLE" if p['visible'] else "hidden"
            print(f"    [{vis}] cls='{p['cls'][:60]}' {p['w']}x{p['h']} z={p['zIndex']} display={p['display']} opacity={p['opacity']}")
            if p['visible']:
                print(f"      Text: {p['text'][:300]}")

        print(f"  Overlays: {len(final_state['overlays'])}")
        for o in final_state['overlays']:
            print(f"    cls='{o['cls'][:40]}' {o['w']}x{o['h']} '{o['text'][:100]}'")

        # ================================================================
        # STEP 8: Try force-showing the float-pro-img panel and mapping it
        # ================================================================
        print("\n[STEP 8] Force-showing float-pro-img panel...")

        force_result = page.evaluate("""() => {
            var proImg = document.querySelector('.c-gen-config.float-pro-img');
            if (!proImg) return {found: false};

            // Hide all other panels first
            for (var el of document.querySelectorAll('.c-gen-config.show')) {
                el.classList.remove('show');
            }

            // Show the product background panel
            proImg.classList.add('show');
            proImg.style.display = '';
            proImg.style.visibility = 'visible';
            proImg.style.opacity = '1';
            proImg.style.zIndex = '9999';

            var r = proImg.getBoundingClientRect();
            return {
                found: true,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: proImg.innerText.substring(0, 2000)
            };
        }""")
        print(f"[STEP 8] Force result: found={force_result.get('found')}")
        if force_result.get('found'):
            print(f"[STEP 8] Panel size: {force_result['w']}x{force_result['h']} at ({force_result['x']},{force_result['y']})")
            print(f"[STEP 8] Panel text:\n{force_result['text'][:1500]}")

            page.wait_for_timeout(500)
            ss(page, "p2_08_float_pro_img_forced")

            # Now do the detailed element mapping
            detailed = map_all_elements_in_region(page, "Product BG Forced Panel",
                                                   force_result['x'] - 10,
                                                   force_result['x'] + force_result['w'] + 10,
                                                   force_result['y'] - 10,
                                                   force_result['y'] + force_result['h'] + 10)

            # Check for image previews / scene thumbnails
            scenes = page.evaluate("""() => {
                var proImg = document.querySelector('.c-gen-config.float-pro-img');
                if (!proImg) return [];
                var items = [];
                for (var el of proImg.querySelectorAll('img')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 20 && r.height > 20) {
                        items.push({
                            src: (el.src || '').substring(0, 150),
                            alt: (el.alt || '').substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)
                        });
                    }
                }
                return items;
            }""")
            print(f"\n[STEP 8b] Scene/template images: {len(scenes)}")
            for s in scenes:
                print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} alt='{s['alt']}' src={s['src'][:80]}")

            # Get the DOM tree of the panel
            dom_tree = page.evaluate("""() => {
                var proImg = document.querySelector('.c-gen-config.float-pro-img');
                if (!proImg) return '';
                function mapEl(el, depth) {
                    if (depth > 5) return '';
                    var className = (typeof el.className === 'string') ? el.className : '';
                    var text = el.childElementCount === 0 ? (el.innerText || '').trim().substring(0, 50) : '';
                    var r = el.getBoundingClientRect();
                    var indent = '  '.repeat(depth);
                    var parts = [indent + el.tagName];
                    if (className) parts.push('cls="' + className.substring(0, 50) + '"');
                    if (el.id) parts.push('id="' + el.id + '"');
                    if (text) parts.push('"' + text + '"');
                    if (r.width > 0) parts.push('(' + Math.round(r.x) + ',' + Math.round(r.y) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + ')');
                    if (el.tagName === 'INPUT') parts.push('type=' + (el.type || ''));
                    var result = parts.join(' ') + '\\n';
                    for (var child of el.children) {
                        result += mapEl(child, depth + 1);
                    }
                    return result;
                }
                return mapEl(proImg, 0);
            }""")
            print(f"\n[STEP 8c] DOM structure:")
            print(dom_tree[:3000])

        # ================================================================
        # SUMMARY
        # ================================================================
        print("\n" + "=" * 70)
        print("PHASE 153 PART 2 SUMMARY")
        print("=" * 70)
        print(f"Screenshots in: {SCREENSHOT_DIR}")
        for f in sorted(SCREENSHOT_DIR.glob("p2_*.png")):
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.0f} KB)")

    except Exception as exc:
        print(f"\n[P153b] FATAL ERROR: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            pw.stop()
        except Exception:
            pass


def main_part3():
    """Part 3: Deep-map the Product Background panel (Template/Prompt/Image tabs),
    close the Remove Background dialog, and try generating."""
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running

    print("=" * 70)
    print("PHASE 153 PART 3: Product Background — Deep UI Map + Generation Test")
    print("=" * 70)

    if not is_browser_running():
        print("[P153c] ERROR: Brave not running")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P153c] No Dzine canvas tab found")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)
        close_popups(page)
        page.wait_for_timeout(500)

        # ================================================================
        # STEP 1: Ensure we have the Product Background panel open
        # ================================================================
        print("\n[STEP 1] Checking if Product Background panel is already open...")

        panel_check = page.evaluate("""() => {
            var el = document.querySelector('.c-gen-config.show');
            if (el && el.innerText.startsWith('Product Background')) {
                return {open: true, cls: (typeof el.className === 'string') ? el.className : ''};
            }
            return {open: false};
        }""")

        if not panel_check['open']:
            print("[STEP 1] Panel not open. Opening Image Editor -> Background...")
            close_panels(page)
            page.wait_for_timeout(500)

            # Select a layer first (click on canvas image)
            page.mouse.click(500, 400)
            page.wait_for_timeout(800)

            # Open Image Editor
            page.mouse.click(40, 674)
            page.wait_for_timeout(2500)

            # Scroll down
            page.evaluate("""() => {
                var el = document.querySelector('.subtools');
                if (el) el.scrollTop = el.scrollHeight;
            }""")
            page.wait_for_timeout(800)

            # Click Background subtool
            page.evaluate("""() => {
                var items = document.querySelectorAll('.subtool-item');
                for (var item of items) {
                    if ((item.innerText || '').includes('Background')) {
                        item.click();
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(3000)
        else:
            print("[STEP 1] Product Background panel is already open.")

        # Close the "Remove Background" dialog if present
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Done') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)
        close_popups(page)
        page.wait_for_timeout(500)

        ss(page, "p3_01_panel_open_clean")

        # ================================================================
        # STEP 2: Map the panel header and tabs
        # ================================================================
        print("\n[STEP 2] Mapping panel header and tabs...")

        header_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var result = {
                header: null,
                tabs: [],
                sourcePreview: null,
                backButton: null,
                closeButton: null,
                helpIcon: null
            };

            // Header
            var header = panel.querySelector('.gen-config-header');
            if (header) {
                var r = header.getBoundingClientRect();
                result.header = {
                    text: (header.innerText || '').trim().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)
                };
            }

            // Back button
            var back = panel.querySelector('.gen-config-header .icon-back, .gen-config-header .ico-back, .gen-config-header button:first-child');
            if (back) {
                var r = back.getBoundingClientRect();
                result.backButton = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }

            // Close button
            var close = panel.querySelector('.ico-close');
            if (close) {
                var r = close.getBoundingClientRect();
                result.closeButton = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }

            // Help icon
            var help = panel.querySelector('.icon-help, .ico-help, [class*="help"]');
            if (help) {
                var r = help.getBoundingClientRect();
                result.helpIcon = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }

            // Tabs
            for (var tab of panel.querySelectorAll('.tab-item, [role="tab"], button')) {
                var text = (tab.innerText || '').trim();
                if (['Template', 'Prompt', 'Image'].includes(text)) {
                    var r = tab.getBoundingClientRect();
                    var className = (typeof tab.className === 'string') ? tab.className : '';
                    result.tabs.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: className.substring(0, 60),
                        active: className.includes('active') || className.includes('selected')
                    });
                }
            }

            // Source Preview
            var preview = panel.querySelector('[class*="source"], [class*="preview"]');
            if (preview) {
                var r = preview.getBoundingClientRect();
                result.sourcePreview = {
                    text: (preview.innerText || '').trim().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (typeof preview.className === 'string') ? preview.className.substring(0, 60) : ''
                };
            }

            return result;
        }""")
        print(f"[STEP 2] Header: {json.dumps(header_info, indent=2)}")

        # ================================================================
        # STEP 3: Map the Template tab in detail
        # ================================================================
        print("\n[STEP 3] Mapping Template tab categories and items...")

        template_data = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var categories = [];
            var currentCategory = null;

            // Find the scrollable content area
            var content = panel.querySelector('.gen-config-body, .gen-config-form');
            if (!content) content = panel;

            // Get all category headers and items
            for (var el of content.querySelectorAll('*')) {
                var className = (typeof el.className === 'string') ? el.className : '';
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();

                // Category title
                if ((className.includes('category-title') || className.includes('group-title') ||
                     className.includes('section-title') || el.tagName === 'H5' || el.tagName === 'H6') &&
                    text.length > 2 && text.length < 40 && el.childElementCount <= 1 && r.width > 0) {
                    currentCategory = {
                        name: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        cls: className.substring(0, 50),
                        items: []
                    };
                    categories.push(currentCategory);
                }
            }

            // If no categories found, try broader approach
            if (categories.length === 0) {
                // Look for item groups by visual layout
                var allItems = [];
                for (var el of content.querySelectorAll('[class*="item"], [class*="thumbnail"], [class*="card"]')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    var className = (typeof el.className === 'string') ? el.className : '';
                    if (r.width > 30 && r.height > 30 && r.x > 80 && r.x < 400 &&
                        text.length > 0 && text.length < 40) {
                        var img = el.querySelector('img');
                        allItems.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: className.substring(0, 50),
                            hasImage: !!img,
                            imgSrc: img ? img.src.substring(0, 100) : '',
                            selected: className.includes('active') || className.includes('selected')
                        });
                    }
                }
                return {categories: [], items: allItems};
            }

            return {categories: categories, items: []};
        }""")
        print(f"[STEP 3] Template data: {json.dumps(template_data, indent=2)[:2000]}")

        # Get ALL visible text elements in the panel body for complete mapping
        all_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                var className = (typeof el.className === 'string') ? el.className : '';
                if (r.width > 0 && r.height > 0 && text.length > 0 && text.length < 50 &&
                    el.childElementCount === 0 && r.y > 50) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        cls: className.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        clickable: el.tagName === 'BUTTON' || className.includes('item') || el.onclick !== null
                    });
                }
            }
            // Deduplicate by position
            var seen = new Set();
            return items.filter(i => {
                var key = i.x + ',' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y || a.x - b.x);
        }""")
        print(f"\n[STEP 3b] All panel text elements (sorted by y): {len(all_text)}")
        current_section = ""
        for t in all_text:
            # Detect section headers (wider elements, often at left edge)
            if t['w'] > 150 and t['x'] < 120:
                current_section = t['text']
                print(f"\n  === {t['text']} === ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> cls='{t['cls'][:30]}'")
            else:
                click = " [clickable]" if t['clickable'] else ""
                print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}'{click}")

        # ================================================================
        # STEP 4: Scroll panel to see all categories
        # ================================================================
        print("\n[STEP 4] Scrolling panel to map ALL template categories...")

        # Find the scrollable container in the panel
        scroll_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            for (var el of panel.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 30 && el.clientHeight > 100) {
                    var r = el.getBoundingClientRect();
                    var className = (typeof el.className === 'string') ? el.className : '';
                    return {
                        cls: className.substring(0, 60),
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    };
                }
            }
            return null;
        }""")
        print(f"[STEP 4] Scroll container: {json.dumps(scroll_info)}")

        # Scroll to bottom to see all categories
        if scroll_info:
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                for (var el of panel.querySelectorAll('*')) {
                    if (el.scrollHeight > el.clientHeight + 30 && el.clientHeight > 100) {
                        el.scrollTop = el.scrollHeight;
                        return;
                    }
                }
            }""")
            page.wait_for_timeout(1000)
            ss(page, "p3_02_template_scrolled_bottom")

            # Map all items after scroll
            bottom_text = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return [];
                var items = [];
                for (var el of panel.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    var className = (typeof el.className === 'string') ? el.className : '';
                    if (r.width > 0 && r.height > 0 && text.length > 0 && text.length < 50 &&
                        el.childElementCount === 0 && r.y > 50) {
                        items.push({text: text, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
                    }
                }
                var seen = new Set();
                return items.filter(i => {
                    var key = i.x + ',' + i.y;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).sort((a, b) => a.y - b.y || a.x - b.x);
            }""")
            print(f"[STEP 4b] Bottom section text: {len(bottom_text)}")
            for t in bottom_text:
                if t['w'] > 150 and t['x'] < 120:
                    print(f"\n  === {t['text']} ===")
                else:
                    print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}'")

        # ================================================================
        # STEP 5: Click "Prompt" tab
        # ================================================================
        print("\n[STEP 5] Switching to Prompt tab...")

        # Scroll back to top first
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            for (var el of panel.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 30 && el.clientHeight > 100) {
                    el.scrollTop = 0;
                    return;
                }
            }
        }""")
        page.wait_for_timeout(500)

        prompt_clicked = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            for (var el of panel.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Prompt' && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.y > 350 && r.y < 420) {
                        el.click();
                        return {x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            return false;
        }""")
        print(f"[STEP 5] Prompt tab clicked: {json.dumps(prompt_clicked)}")
        page.wait_for_timeout(1500)

        ss(page, "p3_03_prompt_tab")

        # Map the prompt tab content
        prompt_content = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var result = {
                textareas: [],
                buttons: [],
                labels: [],
                switches: [],
                allElements: []
            };

            for (var el of panel.querySelectorAll('textarea, input[type="text"], [contenteditable="true"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0) {
                    result.textareas.push({
                        tag: el.tagName,
                        placeholder: (el.placeholder || el.getAttribute('data-placeholder') || '').substring(0, 80),
                        value: (el.value || el.innerText || '').substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                        maxLength: el.maxLength || 0
                    });
                }
            }

            for (var el of panel.querySelectorAll('button')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.y > 350) {
                    var className = (typeof el.className === 'string') ? el.className : '';
                    result.buttons.push({
                        text: text.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: className.substring(0, 60),
                        disabled: el.disabled,
                        id: el.id || ''
                    });
                }
            }

            // All visible elements in the tab area
            for (var el of panel.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.height > 0 && text.length > 0 && text.length < 60 &&
                    el.childElementCount === 0 && r.y > 370 && r.y < 900) {
                    var className = (typeof el.className === 'string') ? el.className : '';
                    result.allElements.push({
                        tag: el.tagName,
                        text: text,
                        cls: className.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }

            // Deduplicate allElements
            var seen = new Set();
            result.allElements = result.allElements.filter(i => {
                var key = i.x + ',' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);

            return result;
        }""")
        print(f"[STEP 5b] Prompt tab content:")
        print(f"  Textareas: {json.dumps(prompt_content.get('textareas', []), indent=2)}")
        print(f"  Buttons: {json.dumps(prompt_content.get('buttons', []), indent=2)}")
        print(f"\n  All elements in Prompt tab area:")
        for e in (prompt_content or {}).get('allElements', []):
            print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text']}' cls='{e['cls']}'")

        # ================================================================
        # STEP 6: Click "Image" tab
        # ================================================================
        print("\n[STEP 6] Switching to Image tab...")

        image_clicked = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            for (var el of panel.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Image' && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.y > 350 && r.y < 420) {
                        el.click();
                        return {x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            return false;
        }""")
        print(f"[STEP 6] Image tab clicked: {json.dumps(image_clicked)}")
        page.wait_for_timeout(1500)

        ss(page, "p3_04_image_tab")

        # Map Image tab content
        image_content = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var result = {allElements: [], fileInputs: [], uploads: []};

            for (var el of panel.querySelectorAll('input[type="file"]')) {
                result.fileInputs.push({
                    accept: el.accept || '',
                    multiple: el.multiple,
                    cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                    id: el.id || ''
                });
            }

            for (var el of panel.querySelectorAll('[class*="upload"], [class*="drop"], button.upload')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.y > 350) {
                    var className = (typeof el.className === 'string') ? el.className : '';
                    result.uploads.push({
                        text: (el.innerText || '').trim().substring(0, 60),
                        cls: className.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }

            for (var el of panel.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.height > 0 && text.length > 0 && text.length < 60 &&
                    el.childElementCount === 0 && r.y > 370 && r.y < 900) {
                    var className = (typeof el.className === 'string') ? el.className : '';
                    result.allElements.push({
                        tag: el.tagName,
                        text: text,
                        cls: className.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }

            var seen = new Set();
            result.allElements = result.allElements.filter(i => {
                var key = i.x + ',' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);

            return result;
        }""")
        print(f"[STEP 6b] Image tab content:")
        print(f"  File inputs: {json.dumps(image_content.get('fileInputs', []))}")
        print(f"  Upload areas: {json.dumps(image_content.get('uploads', []), indent=2)}")
        print(f"\n  All elements in Image tab area:")
        for e in (image_content or {}).get('allElements', []):
            print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text']}' cls='{e['cls']}'")

        # ================================================================
        # STEP 7: Switch back to Template tab and find the Generate button
        # ================================================================
        print("\n[STEP 7] Switching back to Template tab, looking for Generate button...")

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            for (var el of panel.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Template' && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.y > 350 && r.y < 420) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Look for Generate button
        gen_btn = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            // Check for floating generate button
            var floatBtn = panel.querySelector('.float-gen-btn button, button.generative, button[class*="generate"], .consume-tip');
            if (floatBtn) {
                var r = floatBtn.getBoundingClientRect();
                return {
                    text: (floatBtn.innerText || '').trim(),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (typeof floatBtn.className === 'string') ? floatBtn.className.substring(0, 60) : '',
                    disabled: floatBtn.disabled,
                    id: floatBtn.id || ''
                };
            }

            // Check all buttons for "Generate" text
            for (var btn of panel.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                if (text.includes('Generate') || text.includes('credits')) {
                    var r = btn.getBoundingClientRect();
                    if (r.width > 0) {
                        return {
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (typeof btn.className === 'string') ? btn.className.substring(0, 60) : '',
                            disabled: btn.disabled,
                            id: btn.id || ''
                        };
                    }
                }
            }

            return null;
        }""")
        print(f"[STEP 7] Generate button: {json.dumps(gen_btn)}")

        # Also check for floating button at the bottom of the panel
        float_btn = page.evaluate("""() => {
            // Look for any button with "Generate" or credit info, anywhere
            var results = [];
            for (var btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (r.width > 100 && r.height > 30 && r.y > 800 && r.x > 70 && r.x < 400 &&
                    (text.includes('Generate') || text.includes('credit'))) {
                    var className = (typeof btn.className === 'string') ? btn.className : '';
                    results.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: className.substring(0, 60),
                        disabled: btn.disabled
                    });
                }
            }
            return results;
        }""")
        print(f"[STEP 7b] Floating buttons at bottom: {json.dumps(float_btn, indent=2)}")

        # Check for the generate button in the panel's float-gen-btn container
        float_gen = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var container = panel.querySelector('[class*="float-gen"]');
            if (container) {
                var r = container.getBoundingClientRect();
                var btn = container.querySelector('button');
                var btnInfo = null;
                if (btn) {
                    var br = btn.getBoundingClientRect();
                    btnInfo = {
                        text: (btn.innerText || '').trim(),
                        x: Math.round(br.x), y: Math.round(br.y),
                        w: Math.round(br.width), h: Math.round(br.height),
                        disabled: btn.disabled,
                        cls: (typeof btn.className === 'string') ? btn.className.substring(0, 60) : ''
                    };
                }
                return {
                    container: {
                        cls: (typeof container.className === 'string') ? container.className.substring(0, 60) : '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (container.innerText || '').trim().substring(0, 100)
                    },
                    button: btnInfo
                };
            }
            return null;
        }""")
        print(f"[STEP 7c] Float-gen container: {json.dumps(float_gen, indent=2)}")

        ss(page, "p3_05_template_with_generate")

        # ================================================================
        # STEP 8: Try selecting a template and generating
        # ================================================================
        print("\n[STEP 8] Selecting 'White' template and attempting generation...")

        # Click on "White" template (first item in White Background category)
        white_clicked = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            // Find items with class containing 'item' and text 'White'
            for (var el of panel.querySelectorAll('[class*="item"], [class*="template"], [class*="thumb"]')) {
                var text = (el.innerText || '').trim();
                if (text === 'White') {
                    var r = el.getBoundingClientRect();
                    if (r.width > 30 && r.height > 30 && r.y > 400) {
                        el.click();
                        return {
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : ''
                        };
                    }
                }
            }
            return null;
        }""")
        print(f"[STEP 8] White template clicked: {json.dumps(white_clicked)}")
        page.wait_for_timeout(2000)

        ss(page, "p3_06_white_template_selected")

        # Check if Generate button became enabled
        gen_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var btns = [];
            for (var btn of panel.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                if (text.includes('Generate') || text.includes('credit')) {
                    var r = btn.getBoundingClientRect();
                    btns.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        disabled: btn.disabled,
                        cls: (typeof btn.className === 'string') ? btn.className.substring(0, 60) : ''
                    });
                }
            }
            return btns;
        }""")
        print(f"[STEP 8b] Generate buttons state: {json.dumps(gen_state, indent=2)}")

        # Click Generate if we found it and it's enabled
        if gen_state and len(gen_state) > 0:
            for gb in gen_state:
                if not gb['disabled'] and gb['w'] > 50:
                    print(f"[STEP 8c] Clicking Generate: '{gb['text']}' at ({gb['x']},{gb['y']})")
                    page.mouse.click(gb['x'] + gb['w'] // 2, gb['y'] + gb['h'] // 2)
                    page.wait_for_timeout(2000)
                    ss(page, "p3_07_generate_clicked")

                    # Monitor generation progress
                    for i in range(20):
                        progress = page.evaluate("""() => {
                            // Check for progress indicators
                            var spinner = document.querySelector('.spinner, [class*="loading"], [class*="progress"]');
                            var processing = document.querySelector('[class*="processing"], [class*="generating"]');
                            var result = document.querySelector('.result-item:last-child img, .generation-result img');

                            // Check toast/notification
                            var toast = document.querySelector('.toast, [class*="toast"], [class*="notification"]');
                            var toastText = toast ? (toast.innerText || '').trim() : '';

                            // Check result panel for new items
                            var resultPanel = document.querySelector('.result-panel, [class*="result"]');
                            var resultText = resultPanel ? (resultPanel.innerText || '').substring(0, 200) : '';

                            return {
                                hasSpinner: !!spinner,
                                hasProcessing: !!processing,
                                hasResult: !!result,
                                toast: toastText.substring(0, 100),
                                resultText: resultText.substring(0, 200)
                            };
                        }""")
                        status = "spinning" if progress['hasSpinner'] else "done" if progress['hasResult'] else "waiting"
                        print(f"    [{i*3}s] {status} toast='{progress['toast'][:50]}'")
                        if progress['hasResult'] or (not progress['hasSpinner'] and i > 3):
                            break
                        page.wait_for_timeout(3000)

                    ss(page, "p3_08_generation_result")
                    break

        # ================================================================
        # FINAL: Compile comprehensive selectors
        # ================================================================
        print("\n" + "=" * 70)
        print("PHASE 153 PART 3 — COMPILED SELECTORS & STRUCTURE")
        print("=" * 70)

        selectors = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel || !panel.innerText.startsWith('Product Background')) {
                // Try to find it hidden
                for (var el of document.querySelectorAll('.c-gen-config')) {
                    if ((el.innerText || '').startsWith('Product Background')) {
                        panel = el;
                        break;
                    }
                }
            }
            if (!panel) return {};

            var className = (typeof panel.className === 'string') ? panel.className : '';
            var result = {
                panelSelector: 'c-gen-config.' + className.split(' ').filter(c => c.includes('float-pro-img')).join('.'),
                panelClass: className,
                children: []
            };

            // Get all direct children structure
            function walkChildren(parent, depth) {
                if (depth > 3) return;
                for (var child of parent.children) {
                    var r = child.getBoundingClientRect();
                    var cname = (typeof child.className === 'string') ? child.className : '';
                    var text = child.childElementCount === 0 ? (child.innerText || '').trim().substring(0, 40) : '';
                    if (r.width > 0 || child.tagName === 'INPUT') {
                        result.children.push({
                            depth: depth,
                            tag: child.tagName,
                            cls: cname.substring(0, 60),
                            id: child.id || '',
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)
                        });
                        if (depth < 3) walkChildren(child, depth + 1);
                    }
                }
            }
            walkChildren(panel, 0);

            return result;
        }""")
        print(f"Panel selector: {selectors.get('panelSelector', 'unknown')}")
        print(f"Panel class: {selectors.get('panelClass', 'unknown')[:80]}")
        print(f"\nDOM structure ({len(selectors.get('children', []))} nodes):")
        for c in selectors.get('children', [])[:60]:
            indent = "  " * (c['depth'] + 1)
            extra = ""
            if c['id']:
                extra += f" id={c['id']}"
            if c['text']:
                extra += f" '{c['text']}'"
            print(f"{indent}<{c['tag']}> cls='{c['cls'][:40]}' ({c['x']},{c['y']}) {c['w']}x{c['h']}{extra}")

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Screenshots in: {SCREENSHOT_DIR}")
        for f in sorted(SCREENSHOT_DIR.glob("p3_*.png")):
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.0f} KB)")

    except Exception as exc:
        print(f"\n[P153c] FATAL ERROR: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    if "--part3" in sys.argv:
        main_part3()
    elif "--part2" in sys.argv:
        main_part2()
    else:
        main()
