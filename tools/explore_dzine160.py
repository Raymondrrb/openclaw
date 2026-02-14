#!/usr/bin/env python3
"""Phase 160: Deep exploration of the Txt2Img Style Picker.

Builds on initial run findings:
- Style picker panel: #txt2img-style-panel (.style-main-panel)
- Categories: LI.category-item elements (18 categories)
- Style list container: .style-list-panel
- Search input: .search-input (placeholder "Search styles")
- Create a style: Quick Style + Pro Style options
- Style items visible as named cards with thumbnails

This run: iterate ALL 18 categories, extract ALL style names per category,
test search, document selectors for automation.
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

OUT_DIR = "/tmp/dzine_explore_160"


def ss(page, name):
    page.screenshot(path=f"{OUT_DIR}/{name}.png")
    print(f"  Screenshot: {name}", flush=True)


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT, SIDEBAR

    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 70)
    print("PHASE 160: Txt2Img Style Picker — Complete Catalog")
    print("=" * 70)

    if not is_browser_running():
        print("[P160] ERROR: Brave not running on CDP port.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find or create the canvas page
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
            print(f"[P160] Reusing existing canvas tab: {page.url}")
        else:
            print("[P160] No canvas tab found, opening new one...")
            page = context.new_page()
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)
        print(f"[P160] Canvas: {page.url}")

        # Close popups
        closed = close_all_dialogs(page)
        print(f"[P160] Closed {closed} popups")
        page.wait_for_timeout(500)

        # Close any open panels first
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # 1. ENSURE TXT2IMG IS OPEN, THEN OPEN STYLE PICKER
        # ============================================================
        print(f"\n{'='*60}")
        print("1. OPENING TXT2IMG + STYLE PICKER")
        print(f"{'='*60}")

        # First check if the style picker is already open
        picker_open = page.evaluate("""() => {
            var panel = document.querySelector('#txt2img-style-panel');
            if (panel) {
                var r = panel.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }
            return false;
        }""")

        if not picker_open:
            # Click Txt2Img sidebar
            page.mouse.click(*SIDEBAR["img2img"])
            page.wait_for_timeout(500)
            page.mouse.click(*SIDEBAR["txt2img"])
            page.wait_for_timeout(2000)

            # Close popup if any
            close_all_dialogs(page)
            page.wait_for_timeout(300)

            # Click style button to open picker
            page.evaluate("""() => {
                var btn = document.querySelector('.c-style button.style');
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            page.wait_for_timeout(3000)

        # Verify picker is open
        picker_check = page.evaluate("""() => {
            var panel = document.querySelector('#txt2img-style-panel');
            if (!panel) return {open: false, error: 'no panel element'};
            var r = panel.getBoundingClientRect();
            if (r.width === 0) return {open: false, error: 'panel has zero width'};
            return {
                open: true,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height)
            };
        }""")
        print(f"[1] Style picker: {picker_check}")

        if not picker_check.get('open'):
            print("[1] ERROR: Style picker not open. Trying harder...")
            # Try clicking the style area by coordinate (based on previous run)
            page.mouse.click(120, 597)
            page.wait_for_timeout(3000)
            picker_check = page.evaluate("""() => {
                var panel = document.querySelector('#txt2img-style-panel');
                if (!panel) return {open: false};
                var r = panel.getBoundingClientRect();
                return {open: r.width > 0, w: Math.round(r.width), h: Math.round(r.height)};
            }""")
            print(f"[1b] After retry: {picker_check}")

        ss(page, "01_style_picker")

        # ============================================================
        # 2. GET ALL CATEGORY TABS
        # ============================================================
        print(f"\n{'='*60}")
        print("2. CATEGORY TABS")
        print(f"{'='*60}")

        categories = page.evaluate("""() => {
            var items = [];
            var lis = document.querySelectorAll('#txt2img-style-panel .category-item, .style-main-panel .category-item');
            for (var li of lis) {
                var r = li.getBoundingClientRect();
                var text = (li.innerText || '').trim();
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (li.className || '').substring(0, 80),
                    active: li.className.includes('active') || li.className.includes('selected')
                });
            }
            return items;
        }""")
        print(f"[2] Categories: {len(categories)}")
        for c in categories:
            active = " [ACTIVE]" if c['active'] else ""
            print(f"  ({c['x']},{c['y']}) '{c['text']}' cls={c['cls'][:50]}{active}")

        # ============================================================
        # 3. UNDERSTAND THE STYLE LIST STRUCTURE
        # ============================================================
        print(f"\n{'='*60}")
        print("3. STYLE LIST STRUCTURE ANALYSIS")
        print(f"{'='*60}")

        # Get the structure of the right side (style grid area)
        style_grid = page.evaluate("""() => {
            var panel = document.querySelector('#txt2img-style-panel .style-list-panel');
            if (!panel) panel = document.querySelector('.style-list-panel');
            if (!panel) return {error: 'no style-list-panel'};

            var r = panel.getBoundingClientRect();
            var result = {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                childCount: panel.childElementCount,
                sections: []
            };

            // Walk the immediate children to understand layout
            for (var child of panel.children) {
                var cr = child.getBoundingClientRect();
                var text = (child.innerText || '').trim();
                result.sections.push({
                    tag: child.tagName,
                    cls: (child.className || '').substring(0, 60),
                    x: Math.round(cr.x), y: Math.round(cr.y),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                    text: text.substring(0, 200),
                    childCount: child.childElementCount
                });
            }

            return result;
        }""")
        print(f"[3] Style list panel: {style_grid.get('x')},{style_grid.get('y')} {style_grid.get('w')}x{style_grid.get('h')}")
        print(f"[3] Children: {style_grid.get('childCount')}")
        for s in style_grid.get('sections', []):
            print(f"  {s['tag']} cls='{s['cls']}' ({s['x']},{s['y']}) {s['w']}x{s['h']} children={s['childCount']}")
            if s['text']:
                text_preview = s['text'][:120].replace('\n', ' | ')
                print(f"    text: {text_preview}")

        # ============================================================
        # 4. GET "CREATE A STYLE" SECTION DETAILS
        # ============================================================
        print(f"\n{'='*60}")
        print("4. CREATE A STYLE SECTION")
        print(f"{'='*60}")

        create_info = page.evaluate("""() => {
            var results = [];
            var panel = document.querySelector('#txt2img-style-panel') || document.querySelector('.style-main-panel');
            if (!panel) return [];

            var els = panel.querySelectorAll('*');
            for (var el of els) {
                var text = (el.innerText || '').trim();
                if ((text.includes('Create a style') || text.includes('Quick Style') ||
                     text.includes('Pro Style') || text.includes('Dzine Styles') ||
                     text.includes('Community')) && text.length < 100 && el.childElementCount < 5) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        results.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName,
                            cls: (el.className || '').substring(0, 60)
                        });
                    }
                }
            }
            return results;
        }""")
        print(f"[4] Create style elements: {len(create_info)}")
        for c in create_info:
            print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text']}' tag={c['tag']} cls={c['cls']}")

        # ============================================================
        # 5. EXTRACT STYLES FROM "ALL STYLES" CATEGORY FIRST
        # ============================================================
        print(f"\n{'='*60}")
        print("5. ALL STYLES CATEGORY — FULL EXTRACTION")
        print(f"{'='*60}")

        # Click "All styles" tab
        page.evaluate("""() => {
            var lis = document.querySelectorAll('.category-item');
            for (var li of lis) {
                if ((li.innerText || '').trim() === 'All styles') {
                    li.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

        # Now extract ALL style items from the grid
        all_styles_data = page.evaluate("""() => {
            var panel = document.querySelector('.style-list-panel');
            if (!panel) return {error: 'no style-list-panel'};

            // Find the scrollable container within the style list
            var scrollEl = null;
            for (var el of panel.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 50) {
                    scrollEl = el;
                    break;
                }
            }
            if (!scrollEl) scrollEl = panel;

            var info = {
                scrollH: scrollEl.scrollHeight,
                clientH: scrollEl.clientHeight,
                cls: (scrollEl.className || '').substring(0, 60)
            };

            // Collect all style items by scrolling
            var allItems = [];
            var seen = new Set();
            var scrollStep = Math.max(scrollEl.clientHeight * 0.7, 100);
            var maxScrolls = Math.ceil(scrollEl.scrollHeight / scrollStep) + 2;

            for (var i = 0; i <= maxScrolls; i++) {
                scrollEl.scrollTop = i * scrollStep;

                // Find style cards (they typically have an image + text label)
                var cards = scrollEl.querySelectorAll('[class*="style-item"], [class*="item"], .style-card');
                for (var card of cards) {
                    var r = card.getBoundingClientRect();
                    if (r.width < 30 || r.height < 30) continue;

                    var img = card.querySelector('img');
                    var text = (card.innerText || '').trim();
                    var firstName = text.split('\\n')[0].trim();

                    if (firstName.length > 0 && firstName.length < 60 && !seen.has(firstName)) {
                        seen.add(firstName);
                        allItems.push({
                            name: firstName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            hasImg: !!img,
                            cls: (card.className || '').substring(0, 50)
                        });
                    }
                }
            }

            // Reset scroll
            scrollEl.scrollTop = 0;

            return {
                container: info,
                total: allItems.length,
                items: allItems
            };
        }""")

        if all_styles_data.get('error'):
            print(f"[5] Error: {all_styles_data['error']}")
        else:
            print(f"[5] Container: scrollH={all_styles_data['container']['scrollH']} clientH={all_styles_data['container']['clientH']} cls={all_styles_data['container']['cls']}")
            print(f"[5] Total styles in 'All styles': {all_styles_data['total']}")
            for item in all_styles_data.get('items', []):
                img = " [IMG]" if item['hasImg'] else ""
                print(f"  - {item['name']} ({item['w']}x{item['h']}) cls={item['cls'][:30]}{img}")

        ss(page, "05_all_styles")

        # ============================================================
        # 6. ALTERNATIVE: EXTRACT STYLES FROM INNERTEXT OF SECTIONS
        # ============================================================
        print(f"\n{'='*60}")
        print("6. EXTRACT VIA SECTION TEXT PARSING")
        print(f"{'='*60}")

        # The style list panel showed sections like "Dzine Styles" and "Community"
        # Let's get the full text content with section headers
        section_text = page.evaluate("""() => {
            var panel = document.querySelector('.style-list-panel');
            if (!panel) return '';
            return (panel.innerText || '').substring(0, 10000);
        }""")
        print(f"[6] Full style panel text ({len(section_text)} chars):")
        print(section_text[:3000])

        # ============================================================
        # 7. ITERATE EACH CATEGORY AND EXTRACT STYLES
        # ============================================================
        print(f"\n{'='*60}")
        print("7. ITERATING ALL CATEGORIES")
        print(f"{'='*60}")

        catalog = {}
        category_names = [c['text'] for c in categories if c['text']]

        for cat_name in category_names:
            print(f"\n--- Category: '{cat_name}' ---")

            # Click the category
            clicked = page.evaluate("""(catName) => {
                var lis = document.querySelectorAll('.category-item');
                for (var li of lis) {
                    if ((li.innerText || '').trim() === catName) {
                        li.click();
                        return true;
                    }
                }
                return false;
            }""", cat_name)
            if not clicked:
                print(f"  Could not click category '{cat_name}'")
                catalog[cat_name] = {"styles": [], "error": "could not click"}
                continue

            page.wait_for_timeout(1500)

            # Get the full text of the style list panel (which should have updated)
            panel_text = page.evaluate("""() => {
                var panel = document.querySelector('.style-list-panel');
                if (!panel) return '';
                return (panel.innerText || '').substring(0, 10000);
            }""")

            # Parse style names from text (remove known non-style elements)
            raw_lines = [line.strip() for line in panel_text.split('\n') if line.strip()]
            # Filter out known non-style elements
            skip_texts = {
                'Create a style', 'Quick Style', 'Pro Style',
                'Instantly swap a style from one reference image in seconds',
                'Carefully learn a style from reference images in minutes',
                'Dzine Styles', 'Community', 'NEW', 'HOT', 'PRO',
                'Favorites', 'My Styles', 'Recent', 'All styles',
                'General', 'Realistic', 'Illustration', 'Portrait',
                '3D', 'Anime', 'Line Art', 'Material Art',
                'Logo & Icon', 'Character', 'Scene', 'Interior',
                'Tattoo', 'Legacy', 'Search styles',
            }
            style_names = [
                line for line in raw_lines
                if line not in skip_texts
                and len(line) > 1
                and len(line) < 60
                and not line.startswith('Instantly')
                and not line.startswith('Carefully')
            ]

            catalog[cat_name] = {
                "styles": style_names,
                "count": len(style_names),
                "raw_text_len": len(panel_text)
            }
            print(f"  Styles ({len(style_names)}):")
            for s in style_names:
                print(f"    - {s}")

            # Take screenshot for this category
            ss(page, f"07_cat_{cat_name.replace(' ', '_').replace('&', 'and').replace('/', '_')}")

            # If scrollable, scroll down to get more
            more_after_scroll = page.evaluate("""() => {
                var panel = document.querySelector('.style-list-panel');
                if (!panel) return {scrollable: false};

                // Find scrollable child
                var scrollEl = null;
                for (var el of [panel, ...panel.querySelectorAll('*')]) {
                    var cs = window.getComputedStyle(el);
                    if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') &&
                        el.scrollHeight > el.clientHeight + 50) {
                        scrollEl = el;
                        break;
                    }
                }
                if (!scrollEl) return {scrollable: false, scrollH: panel.scrollHeight, clientH: panel.clientHeight};

                // Scroll to bottom and get text
                scrollEl.scrollTop = scrollEl.scrollHeight;
                var text = (panel.innerText || '').substring(0, 10000);
                scrollEl.scrollTop = 0;
                return {
                    scrollable: true,
                    scrollH: scrollEl.scrollHeight,
                    clientH: scrollEl.clientHeight,
                    textAfterScroll: text
                };
            }""")

            if more_after_scroll.get('scrollable'):
                print(f"  [scrollable] scrollH={more_after_scroll['scrollH']} clientH={more_after_scroll['clientH']}")
                after_text = more_after_scroll.get('textAfterScroll', '')
                after_lines = [line.strip() for line in after_text.split('\n') if line.strip()]
                after_styles = [
                    line for line in after_lines
                    if line not in skip_texts
                    and len(line) > 1
                    and len(line) < 60
                    and not line.startswith('Instantly')
                    and not line.startswith('Carefully')
                ]
                # Merge with existing
                existing = set(catalog[cat_name]["styles"])
                new_styles = [s for s in after_styles if s not in existing]
                if new_styles:
                    catalog[cat_name]["styles"].extend(new_styles)
                    catalog[cat_name]["count"] = len(catalog[cat_name]["styles"])
                    print(f"  [scrolled] Found {len(new_styles)} additional styles:")
                    for s in new_styles:
                        print(f"    + {s}")

        # ============================================================
        # 8. SEARCH FUNCTIONALITY TEST
        # ============================================================
        print(f"\n{'='*60}")
        print("8. SEARCH FUNCTIONALITY")
        print(f"{'='*60}")

        # First, make sure we're on "All styles" so search covers everything
        page.evaluate("""() => {
            var lis = document.querySelectorAll('.category-item');
            for (var li of lis) {
                if ((li.innerText || '').trim() === 'All styles') {
                    li.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        search_queries = ["Realistic Product", "Film Narrative", "Nano Banana Pro", "Watercolor", "Cinematic"]
        search_results = {}

        for query in search_queries:
            print(f"\n  Searching for: '{query}'")

            # Focus and type in search input
            typed = page.evaluate("""(q) => {
                var input = document.querySelector('.search-input');
                if (!input) {
                    // Fallback
                    var inputs = document.querySelectorAll('input');
                    for (var inp of inputs) {
                        if (inp.placeholder && inp.placeholder.includes('earch')) {
                            input = inp;
                            break;
                        }
                    }
                }
                if (!input) return {found: false};
                input.focus();
                input.value = q;
                input.dispatchEvent(new Event('input', {bubbles: true}));
                input.dispatchEvent(new Event('change', {bubbles: true}));
                // Also try keyup
                input.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
                return {found: true, x: Math.round(input.getBoundingClientRect().x), y: Math.round(input.getBoundingClientRect().y)};
            }""", query)

            if not typed.get('found'):
                print(f"    Search input not found!")
                search_results[query] = []
                continue

            page.wait_for_timeout(1500)

            # Get visible styles after search
            results = page.evaluate("""() => {
                var panel = document.querySelector('.style-list-panel');
                if (!panel) return [];
                var text = (panel.innerText || '').trim();
                var lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 1 && l.length < 60);
                // Filter out non-style items
                var skip = ['Create a style', 'Quick Style', 'Pro Style', 'Dzine Styles', 'Community',
                           'Instantly swap', 'Carefully learn', 'NEW', 'HOT', 'PRO', 'No results found'];
                return lines.filter(l => !skip.some(s => l.includes(s)));
            }""")
            search_results[query] = results
            print(f"    Results ({len(results)}): {results}")
            ss(page, f"08_search_{query.replace(' ', '_')}")

            # Clear search
            page.evaluate("""() => {
                var input = document.querySelector('.search-input');
                if (!input) {
                    var inputs = document.querySelectorAll('input');
                    for (var inp of inputs) {
                        if (inp.placeholder && inp.placeholder.includes('earch')) { input = inp; break; }
                    }
                }
                if (input) {
                    input.value = '';
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }""")
            page.wait_for_timeout(500)

        # ============================================================
        # 9. AUTOMATION SELECTORS DOCUMENTATION
        # ============================================================
        print(f"\n{'='*60}")
        print("9. AUTOMATION SELECTORS")
        print(f"{'='*60}")

        selectors = page.evaluate("""() => {
            var result = {};

            // Style picker panel
            var panel = document.querySelector('#txt2img-style-panel');
            result.pickerPanel = panel ? '#txt2img-style-panel' : null;

            // Category items
            var cats = document.querySelectorAll('.category-item');
            result.categorySelector = cats.length > 0 ? '.category-item' : null;
            result.categoryCount = cats.length;

            // Search input
            var search = document.querySelector('.search-input');
            result.searchInput = search ? '.search-input' : null;

            // Style items (the clickable cards in the grid)
            var styleItems = document.querySelectorAll('.style-list-panel [class*="item"]');
            result.styleItemSelector = styleItems.length > 0 ? '.style-list-panel [class*="item"]' : null;
            result.styleItemCount = styleItems.length;

            // Individual style item structure
            if (styleItems.length > 0) {
                var first = styleItems[0];
                result.firstItemHTML = first.outerHTML.substring(0, 300);
                result.firstItemCls = (first.className || '').substring(0, 80);
                result.firstItemTag = first.tagName;
            }

            // Close button
            var closeBtn = panel ? panel.querySelector('.ico-close, [class*="close"], button[aria-label="Close"]') : null;
            result.closeSelector = closeBtn ? (closeBtn.className || '').substring(0, 40) : null;

            // Create style buttons
            var createBtns = panel ? panel.querySelectorAll('button') : [];
            result.createStyleBtns = [];
            for (var btn of createBtns) {
                var text = (btn.innerText || '').trim();
                if (text.length > 0 && text.length < 40) {
                    result.createStyleBtns.push({
                        text: text,
                        cls: (btn.className || '').substring(0, 40)
                    });
                }
            }

            // Active/selected style
            var activeItem = panel ? panel.querySelector('[class*="active"], [class*="selected"]') : null;
            if (activeItem) {
                result.activeStyle = {
                    text: (activeItem.innerText || '').trim().substring(0, 50),
                    cls: (activeItem.className || '').substring(0, 60)
                };
            }

            return result;
        }""")
        print("[9] Automation selectors:")
        print(json.dumps(selectors, indent=2))

        # ============================================================
        # 10. STYLE ITEM CLICK MECHANISM
        # ============================================================
        print(f"\n{'='*60}")
        print("10. STYLE ITEM CLICK MECHANISM")
        print(f"{'='*60}")

        # How do we select a style? Check the first few items
        click_mechanism = page.evaluate("""() => {
            var panel = document.querySelector('.style-list-panel');
            if (!panel) return {error: 'no panel'};

            var items = [];
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width >= 60 && r.height >= 60 && r.width <= 200 && r.height <= 200 &&
                    text.length > 0 && text.length < 60 && el.childElementCount <= 5) {
                    // Check if it has click handler or is a button
                    var hasClick = el.onclick !== null || el.tagName === 'BUTTON' ||
                                  (el.getAttribute('role') || '') === 'button' ||
                                  el.style.cursor === 'pointer' ||
                                  window.getComputedStyle(el).cursor === 'pointer';
                    items.push({
                        text: text.split('\\n')[0].trim(),
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        clickable: hasClick,
                        cursor: window.getComputedStyle(el).cursor
                    });
                }
            }
            // Deduplicate by text
            var unique = [], seen = new Set();
            for (var item of items) {
                if (!seen.has(item.text)) { seen.add(item.text); unique.push(item); }
            }
            return unique.slice(0, 20);
        }""")
        print(f"[10] Clickable style items: {len(click_mechanism)}")
        for item in click_mechanism:
            click = " [CLICKABLE]" if item['clickable'] else ""
            print(f"  '{item['text']}' tag={item['tag']} cls={item['cls'][:40]} cursor={item['cursor']}{click}")
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']}")

        # ============================================================
        # 11. TEST SELECTING A SPECIFIC STYLE
        # ============================================================
        print(f"\n{'='*60}")
        print("11. TEST SELECTING A STYLE")
        print(f"{'='*60}")

        # Try to select "Realistic Product"
        select_result = page.evaluate("""() => {
            var panel = document.querySelector('.style-list-panel');
            if (!panel) return {error: 'no panel'};

            // Find the element for "Realistic Product"
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Realistic Product' || text.startsWith('Realistic Product')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 40 && r.height > 40) {
                        el.click();
                        return {
                            clicked: true,
                            text: text,
                            tag: el.tagName,
                            cls: (el.className || '').substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y)
                        };
                    }
                }
            }
            return {clicked: false, error: 'Realistic Product not found in current view'};
        }""")
        print(f"[11] Select 'Realistic Product': {select_result}")
        page.wait_for_timeout(1000)
        ss(page, "11_after_select")

        # Check if the style was actually selected (button text should change)
        after_select = page.evaluate("""() => {
            // Check if picker closed and style name updated in panel
            var styleBtn = document.querySelector('.c-style button.style');
            var styleName = document.querySelector('.style-name');
            return {
                btnText: styleBtn ? (styleBtn.innerText || '').trim() : null,
                nameText: styleName ? (styleName.innerText || '').trim() : null,
                pickerStillOpen: (document.querySelector('#txt2img-style-panel') || {}).getBoundingClientRect
                    ? document.querySelector('#txt2img-style-panel').getBoundingClientRect().width > 0
                    : false
            };
        }""")
        print(f"[11b] After select: {after_select}")

        # ============================================================
        # FINAL SUMMARY
        # ============================================================
        print("\n" + "=" * 70)
        print("PHASE 160 FINAL SUMMARY")
        print("=" * 70)

        summary = {
            "style_picker": {
                "panel_id": "#txt2img-style-panel",
                "panel_class": "style-main-panel",
                "open_via": ".c-style button.style (click) OR coordinate-based click on Style area",
                "close_via": "Escape key OR select a style (auto-closes)",
                "search_input": ".search-input (placeholder='Search styles')",
                "category_selector": "LI.category-item",
            },
            "categories": {},
            "total_unique_styles": 0,
            "search_results": search_results,
            "create_style_options": ["Quick Style", "Pro Style"],
            "automation_selectors": selectors,
            "style_selection_method": "Click the style card element within .style-list-panel",
        }

        all_unique = set()
        for cat_name, data in catalog.items():
            styles = data.get("styles", [])
            summary["categories"][cat_name] = {
                "count": len(styles),
                "styles": styles
            }
            for s in styles:
                all_unique.add(s)

        summary["total_unique_styles"] = len(all_unique)
        summary["all_unique_styles_sorted"] = sorted(all_unique)

        print(f"\n  Total categories: {len(catalog)}")
        print(f"  Total unique styles across all categories: {len(all_unique)}")
        print(f"\n  Categories and counts:")
        for cat_name, data in catalog.items():
            count = data.get("count", len(data.get("styles", [])))
            print(f"    {cat_name}: {count} styles")

        print(f"\n  All unique style names ({len(all_unique)}):")
        for name in sorted(all_unique):
            print(f"    - {name}")

        print(f"\n  Search results:")
        for query, results in search_results.items():
            print(f"    '{query}': {len(results)} matches -> {results}")

        print(f"\n  Create a style options: Quick Style, Pro Style")

        # Save full summary
        summary_path = f"{OUT_DIR}/style_catalog_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\n  Full summary saved to: {summary_path}")
        print(f"  Screenshots in: {OUT_DIR}/")

        ss(page, "99_final")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
