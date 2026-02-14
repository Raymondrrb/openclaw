#!/usr/bin/env python3
"""Phase 157: Explore Dzine "Change Clothes" / "Virtual Try-on" feature.

Goal: Find and document the clothing change functionality — used for wardrobe
changes on the Ray avatar while maintaining facial identity.

Phase 1 (complete): Searched canvas for "Change Clothes" — NOT found as a
sidebar tool, Image Editor sub-tool, or results action. BUT found:
- "Virtual Try-on" on the /aiTools page (row 3, col 3)
- Blog posts: "Change Clothes on a Picture", "Change Dress Using AI"
- The feature is called "Virtual Try-on" in the UI, not "Change Clothes"

Phase 2: Click into Virtual Try-on from AI Tools page, document full UI,
test with Ray avatar image, document all selectors for automation.
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

OUT_DIR = Path("/tmp/dzine_explore_157")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def screenshot(page, name: str) -> str:
    """Take a screenshot and return the path."""
    path = str(OUT_DIR / f"{name}.png")
    page.screenshot(path=path)
    print(f"  [screenshot] {path}")
    return path


def close_popups(page):
    """Close promotional popups."""
    try:
        not_now = page.locator('button:has-text("Not now")')
        if not_now.count() > 0:
            not_now.first.click(timeout=2000)
            page.wait_for_timeout(500)
            print("  [popup] Closed 'Not now' popup")
    except Exception:
        pass
    # Also close any result preview overlay
    try:
        page.evaluate("""() => {
            var preview = document.querySelector('#result-preview');
            if (preview) { preview.remove(); return true; }
            return false;
        }""")
    except Exception:
        pass


def close_panels(page):
    """Close any open panels."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        // Close gen-config panels
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) {
            el.click();
        }
        // Close lip sync panel specifically
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) {
            var close = lsp.querySelector('.ico-close');
            if (close) close.click();
            else lsp.classList.remove('show');
        }
    }""")
    page.wait_for_timeout(500)


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import VIEWPORT, CANVAS_URL

    print("=" * 70)
    print("PHASE 157: Explore 'Change Clothes' Feature")
    print("=" * 70)
    print(f"Output dir: {OUT_DIR}")

    if not is_browser_running():
        print("[P157] ERROR: Brave not running on CDP port.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find or open Dzine canvas
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
            print(f"[P157] Reusing canvas tab: {page.url}")
        else:
            print(f"[P157] Opening canvas: {CANVAS_URL}")
            page = context.new_page()
            page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)
        close_popups(page)
        page.wait_for_timeout(500)

        screenshot(page, "01_initial_canvas")

        # ============================================================
        # STEP 1: Global text search for "Change Clothes" on the page
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 1: Search all visible text for clothing-related features")
        print(f"{'='*60}")

        clothing_text = page.evaluate("""() => {
            var matches = [];
            var keywords = ['change clothes', 'clothes', 'outfit', 'wardrobe',
                           'garment', 'dress up', 'clothing', 'attire', 'costume',
                           'try on', 'fashion', 'wear'];
            var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                var text = walker.currentNode.textContent.trim().toLowerCase();
                for (var kw of keywords) {
                    if (text.includes(kw) && text.length < 200) {
                        var parent = walker.currentNode.parentElement;
                        if (parent) {
                            var r = parent.getBoundingClientRect();
                            if (r.width > 0) {
                                matches.push({
                                    keyword: kw,
                                    text: walker.currentNode.textContent.trim().substring(0, 100),
                                    tag: parent.tagName,
                                    cls: (parent.className || '').substring(0, 60),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    visible: r.width > 0 && r.height > 0
                                });
                            }
                        }
                    }
                }
            }
            // Deduplicate by text
            var seen = new Set();
            return matches.filter(m => {
                var key = m.text + m.x + m.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }""")
        print(f"[1] Found {len(clothing_text)} clothing-related text nodes:")
        for m in clothing_text:
            print(f"  keyword='{m['keyword']}' text='{m['text']}' tag={m['tag']} ({m['x']},{m['y']}) {m['w']}x{m['h']} vis={m['visible']}")

        # ============================================================
        # STEP 2: Check all sidebar tools (12 known + any new ones)
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 2: Enumerate ALL sidebar tool-groups")
        print(f"{'='*60}")

        close_panels(page)
        page.wait_for_timeout(500)

        sidebar_tools = page.evaluate("""() => {
            var tools = [];
            for (var el of document.querySelectorAll('.tool-group, [class*="tool-group"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.x < 80) {
                    tools.push({
                        text: text.replace(/\\n/g, ' | ').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        id: el.id || ''
                    });
                }
            }
            return tools;
        }""")
        print(f"[2] Sidebar tools: {len(sidebar_tools)}")
        for t in sidebar_tools:
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}' cls={t['cls']}")

        # ============================================================
        # STEP 3: Open Image Editor and enumerate ALL sub-tools
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 3: Image Editor — full sub-tool list (including scroll)")
        print(f"{'='*60}")

        # Click Image Editor at (40, 698)
        close_panels(page)
        page.wait_for_timeout(500)
        page.mouse.click(40, 197)  # Click Txt2Img first (distant tool)
        page.wait_for_timeout(800)
        page.mouse.click(40, 698)  # Image Editor
        page.wait_for_timeout(2000)

        screenshot(page, "02_image_editor_panel")

        # Read all sub-tools
        ie_tools = page.evaluate("""() => {
            var tools = [];
            // Check for collapse-option items (Image Editor sub-tools)
            for (var el of document.querySelectorAll('.collapse-option, .subtool-item, [class*="collapse-option"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0) {
                    tools.push({
                        text: text.replace(/\\n/g, ' | ').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        visible: r.y > 0 && r.y < 900
                    });
                }
            }
            return tools;
        }""")
        print(f"[3a] Image Editor tools (before scroll): {len(ie_tools)}")
        for t in ie_tools:
            vis = " [OFFSCREEN]" if not t['visible'] else ""
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}' cls={t['cls']}{vis}")

        # Scroll down in the sub-tools panel
        page.evaluate("""() => {
            var panel = document.querySelector('.subtools');
            if (panel) { panel.scrollTop = panel.scrollHeight; return true; }
            return false;
        }""")
        page.wait_for_timeout(1000)

        ie_tools_after = page.evaluate("""() => {
            var tools = [];
            for (var el of document.querySelectorAll('.collapse-option, .subtool-item, [class*="collapse-option"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0) {
                    tools.push({
                        text: text.replace(/\\n/g, ' | ').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        visible: r.y > 0 && r.y < 900
                    });
                }
            }
            return tools;
        }""")
        print(f"\n[3b] Image Editor tools (after scroll): {len(ie_tools_after)}")
        for t in ie_tools_after:
            vis = " [OFFSCREEN]" if not t['visible'] else ""
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}' cls={t['cls']}{vis}")

        screenshot(page, "03_image_editor_scrolled")

        # Also get ALL text in the Image Editor panel
        ie_all_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show') ||
                        document.querySelector('.panels.show');
            if (!panel) return null;
            return panel.innerText;
        }""")
        if ie_all_text:
            print(f"\n[3c] Full Image Editor panel text:")
            for line in ie_all_text.split('\n'):
                line = line.strip()
                if line:
                    print(f"  {line}")

        # ============================================================
        # STEP 4: Check the full list of section headers in Image Editor
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 4: Image Editor section headers")
        print(f"{'='*60}")

        ie_sections = page.evaluate("""() => {
            var sections = [];
            var panel = document.querySelector('.c-gen-config.show') ||
                        document.querySelector('.panels.show');
            if (!panel) return sections;

            for (var el of panel.querySelectorAll('h3, h4, h5, .section-title, .group-title, [class*="title"], [class*="header"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 0 && text.length < 50) {
                    sections.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            return sections;
        }""")
        print(f"[4] Section headers: {len(ie_sections)}")
        for s in ie_sections:
            print(f"  ({s['x']},{s['y']}) '{s['text']}' tag={s['tag']} cls={s['cls']}")

        # ============================================================
        # STEP 5: Check Results panel for clothing-related actions
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 5: Results panel action buttons (all types)")
        print(f"{'='*60}")

        close_panels(page)
        page.wait_for_timeout(500)

        # Click Results tab
        page.evaluate("""() => {
            var tab = document.querySelector('.header-item.item-result');
            if (tab) { tab.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Read ALL label-text items in results panel
        result_actions = page.evaluate("""() => {
            var actions = [];
            for (var el of document.querySelectorAll('.label-text, [class*="label-text"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.x > 1000) {
                    actions.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width)
                    });
                }
            }
            // Also check for any "Change Clothes" or similar in the broader area
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                var r = el.getBoundingClientRect();
                if (r.x > 1000 && r.width > 0 && r.height > 0 && r.height < 40 &&
                    (text.includes('change clothes') || text.includes('outfit') ||
                     text.includes('wardrobe') || text.includes('clothing') ||
                     text.includes('dress') || text.includes('costume'))) {
                    actions.push({
                        text: (el.innerText || '').trim(),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        cls: (el.className || '').substring(0, 40),
                        special: true
                    });
                }
            }
            return actions;
        }""")
        print(f"[5] Results panel actions: {len(result_actions)}")
        for a in result_actions:
            special = " *** CLOTHING-RELATED ***" if a.get('special') else ""
            print(f"  ({a['x']},{a['y']}) w={a['w']} '{a['text']}'{special}")

        screenshot(page, "04_results_panel")

        # Scroll results panel to find more actions
        page.evaluate("""() => {
            var panel = document.querySelector('.result-panel') ||
                        document.querySelector('[class*="result"]');
            if (panel && panel.scrollHeight > panel.clientHeight) {
                panel.scrollTop = 0;
                return {scrollH: panel.scrollHeight, clientH: panel.clientHeight};
            }
            return null;
        }""")
        page.wait_for_timeout(500)

        # ============================================================
        # STEP 6: Check top toolbar / layer tools bar
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 6: Top toolbar / Layer tools bar")
        print(f"{'='*60}")

        # Get all tool-items in top bar
        toolbar_items = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button.tool-item, .item.tool-item, [class*="tool-item"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || el.getAttribute('title') || el.getAttribute('aria-label') || '').trim();
                if (r.width > 0 && r.y < 60) {
                    // Also check tooltip/title on child elements
                    var childTitle = '';
                    for (var child of el.querySelectorAll('*')) {
                        childTitle = childTitle || child.getAttribute('title') || child.getAttribute('aria-label') || '';
                    }
                    items.push({
                        text: text.substring(0, 60) || childTitle.substring(0, 60) || '[no text]',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            return items;
        }""")
        print(f"[6] Top toolbar items: {len(toolbar_items)}")
        for t in toolbar_items:
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}' cls={t['cls']}")

        # ============================================================
        # STEP 7: Search Dzine AI Tools page for Change Clothes
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 7: Check Dzine AI Tools page for clothing tools")
        print(f"{'='*60}")

        # Navigate to /aiTools in a new tab
        ai_tools_page = context.new_page()
        ai_tools_page.set_viewport_size(VIEWPORT)
        try:
            ai_tools_page.goto("https://www.dzine.ai/aiTools", wait_until="domcontentloaded", timeout=20000)
            ai_tools_page.wait_for_timeout(3000)
            close_popups(ai_tools_page)
            ai_tools_page.wait_for_timeout(500)

            screenshot_path = str(OUT_DIR / "05_ai_tools_page.png")
            ai_tools_page.screenshot(path=screenshot_path)
            print(f"  [screenshot] {screenshot_path}")

            # Search for clothing-related tools on the AI Tools page
            ai_tools_text = ai_tools_page.evaluate("""() => {
                var all_text = document.body.innerText;
                var lines = all_text.split('\\n').filter(l => l.trim().length > 0);
                return lines.map(l => l.trim()).slice(0, 200);
            }""")
            print(f"[7a] AI Tools page text ({len(ai_tools_text)} lines):")
            clothing_found = False
            for line in ai_tools_text:
                lower = line.lower()
                if any(kw in lower for kw in ['clothes', 'outfit', 'wardrobe', 'dress', 'clothing',
                                                'fashion', 'costume', 'wear', 'garment', 'attire',
                                                'change clothes']):
                    print(f"  *** {line}")
                    clothing_found = True
                elif len(line) < 80:
                    print(f"  {line}")

            # Also look for tool cards/buttons
            ai_tool_cards = ai_tools_page.evaluate("""() => {
                var cards = [];
                for (var el of document.querySelectorAll('a, button, [class*="card"], [class*="tool"]')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (r.width > 50 && r.height > 50 && r.y > 0 && r.y < 2000) {
                        if (text.includes('cloth') || text.includes('outfit') ||
                            text.includes('dress') || text.includes('fashion') ||
                            text.includes('wear') || text.includes('try on') ||
                            text.includes('wardrobe') || text.includes('change clothes')) {
                            cards.push({
                                text: (el.innerText || '').trim().substring(0, 100),
                                tag: el.tagName,
                                href: el.href || '',
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                cls: (el.className || '').substring(0, 60)
                            });
                        }
                    }
                }
                return cards;
            }""")
            if ai_tool_cards:
                print(f"\n[7b] Clothing-related tool cards: {len(ai_tool_cards)}")
                for c in ai_tool_cards:
                    print(f"  '{c['text']}' href={c['href']} ({c['x']},{c['y']}) {c['w']}x{c['h']}")
            else:
                print(f"\n[7b] No clothing-related tool cards found on AI Tools page")

            # Scroll the page and search again
            ai_tools_page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            ai_tools_page.wait_for_timeout(2000)

            screenshot_path2 = str(OUT_DIR / "06_ai_tools_scrolled.png")
            ai_tools_page.screenshot(path=screenshot_path2)
            print(f"  [screenshot] {screenshot_path2}")

            ai_tool_cards2 = ai_tools_page.evaluate("""() => {
                var cards = [];
                for (var el of document.querySelectorAll('a, button, [class*="card"], [class*="tool"]')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (r.width > 50 && r.height > 50) {
                        if (text.includes('cloth') || text.includes('outfit') ||
                            text.includes('dress') || text.includes('fashion') ||
                            text.includes('try on') || text.includes('wardrobe') ||
                            text.includes('change clothes')) {
                            cards.push({
                                text: (el.innerText || '').trim().substring(0, 100),
                                tag: el.tagName,
                                href: el.href || '',
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height)
                            });
                        }
                    }
                }
                return cards;
            }""")
            if ai_tool_cards2:
                print(f"\n[7c] After scroll clothing cards: {len(ai_tool_cards2)}")
                for c in ai_tool_cards2:
                    print(f"  '{c['text']}' href={c['href']} ({c['x']},{c['y']}) {c['w']}x{c['h']}")

            # Get ALL tool names on the page
            all_tool_names = ai_tools_page.evaluate("""() => {
                var names = [];
                for (var el of document.querySelectorAll('h2, h3, h4, [class*="title"], [class*="name"]')) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 60) {
                        names.push(text);
                    }
                }
                return [...new Set(names)];
            }""")
            print(f"\n[7d] All tool names on AI Tools page: {len(all_tool_names)}")
            for name in all_tool_names:
                marker = " ***" if any(kw in name.lower() for kw in ['cloth', 'outfit', 'dress', 'fashion', 'wear', 'wardrobe']) else ""
                print(f"  {name}{marker}")

        except Exception as e:
            print(f"[7] AI Tools page error: {e}")
        finally:
            try:
                ai_tools_page.close(run_before_unload=False)
            except Exception:
                pass

        # ============================================================
        # STEP 8: Check Dzine's /tools/ pages for clothing features
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 8: Check /tools/ landing pages")
        print(f"{'='*60}")

        tools_page = context.new_page()
        tools_page.set_viewport_size(VIEWPORT)
        try:
            # Try /tools/change-clothes or /tools/ai-change-clothes
            for url_path in [
                "https://www.dzine.ai/tools/change-clothes/",
                "https://www.dzine.ai/tools/ai-change-clothes/",
                "https://www.dzine.ai/tools/virtual-try-on/",
                "https://www.dzine.ai/tools/outfit-change/",
            ]:
                print(f"\n[8] Trying: {url_path}")
                try:
                    resp = tools_page.goto(url_path, wait_until="domcontentloaded", timeout=10000)
                    status = resp.status if resp else "no response"
                    final_url = tools_page.url
                    print(f"  Status: {status}, Final URL: {final_url}")
                    if resp and resp.status == 200:
                        tools_page.wait_for_timeout(2000)
                        close_popups(tools_page)
                        screenshot(tools_page, f"08_tools_{url_path.split('/')[-2]}")

                        page_title = tools_page.evaluate("() => document.title")
                        page_h1 = tools_page.evaluate("""() => {
                            var h1 = document.querySelector('h1');
                            return h1 ? h1.innerText.trim() : null;
                        }""")
                        print(f"  Title: {page_title}")
                        print(f"  H1: {page_h1}")
                except Exception as e:
                    print(f"  Error: {e}")

        except Exception as e:
            print(f"[8] Tools page error: {e}")
        finally:
            try:
                tools_page.close(run_before_unload=False)
            except Exception:
                pass

        # ============================================================
        # STEP 9: Back to canvas — check if CC results have new actions
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 9: Deep scan of results panel for ALL action labels")
        print(f"{'='*60}")

        page.bring_to_front()
        page.wait_for_timeout(1000)
        close_popups(page)

        # Click Results tab
        page.evaluate("""() => {
            var tab = document.querySelector('.header-item.item-result');
            if (tab) { tab.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Get every single text element in the results panel area (x > 1000)
        all_result_text = page.evaluate("""() => {
            var items = [];
            var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                var text = walker.currentNode.textContent.trim();
                if (text.length > 0 && text.length < 100) {
                    var parent = walker.currentNode.parentElement;
                    if (parent) {
                        var r = parent.getBoundingClientRect();
                        if (r.x > 1000 && r.width > 0 && r.height > 0 && r.y > 0 && r.y < 900) {
                            items.push({
                                text: text,
                                tag: parent.tagName,
                                x: Math.round(r.x), y: Math.round(r.y),
                                cls: (parent.className || '').substring(0, 40)
                            });
                        }
                    }
                }
            }
            // Deduplicate
            var seen = new Set();
            return items.filter(i => {
                var key = i.text + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }""")
        print(f"[9] All text in results area: {len(all_result_text)} items")
        for item in all_result_text:
            marker = ""
            lower = item['text'].lower()
            if any(kw in lower for kw in ['cloth', 'outfit', 'dress', 'fashion', 'wear', 'wardrobe', 'costume']):
                marker = " *** CLOTHING ***"
            print(f"  ({item['x']},{item['y']}) '{item['text']}' tag={item['tag']}{marker}")

        # Scroll the results panel
        scrolled = page.evaluate("""() => {
            var panels = document.querySelectorAll('.material-v2-result-content, [class*="result-content"], .result-panel');
            for (var p of panels) {
                if (p.scrollHeight > p.clientHeight + 50) {
                    p.scrollTop = p.scrollHeight;
                    return {tag: p.tagName, cls: (p.className || '').substring(0, 40),
                            scrollH: p.scrollHeight, clientH: p.clientHeight};
                }
            }
            return null;
        }""")
        if scrolled:
            print(f"\n[9b] Scrolled results: {scrolled}")
            page.wait_for_timeout(1000)

            more_text = page.evaluate("""() => {
                var items = [];
                var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                while (walker.nextNode()) {
                    var text = walker.currentNode.textContent.trim();
                    if (text.length > 0 && text.length < 100) {
                        var parent = walker.currentNode.parentElement;
                        if (parent) {
                            var r = parent.getBoundingClientRect();
                            if (r.x > 1000 && r.width > 0 && r.height > 0 && r.y > 0 && r.y < 900) {
                                items.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
                            }
                        }
                    }
                }
                var seen = new Set();
                return items.filter(i => {
                    var key = i.text + '|' + i.y;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                });
            }""")
            print(f"[9c] After scroll: {len(more_text)} items")
            for item in more_text:
                marker = ""
                lower = item['text'].lower()
                if any(kw in lower for kw in ['cloth', 'outfit', 'dress', 'fashion', 'wear', 'wardrobe', 'costume']):
                    marker = " *** CLOTHING ***"
                print(f"  ({item['x']},{item['y']}) '{item['text']}'{marker}")

        screenshot(page, "07_results_all_actions")

        # ============================================================
        # STEP 10: Check layer tools bar when an image is selected
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 10: Layer tools bar (select canvas image first)")
        print(f"{'='*60}")

        # Click on the canvas center to select an image layer
        page.mouse.click(700, 450)
        page.wait_for_timeout(1000)

        layer_tools = page.evaluate("""() => {
            var items = [];
            // layer-tools bar items
            for (var el of document.querySelectorAll('.layer-tools *, .item[class*="tool"], [class*="layer-tool"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || el.getAttribute('title') || '').trim();
                if (r.width > 0 && r.height > 0 && text.length > 0 && text.length < 40 &&
                    el.childElementCount === 0) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            // Deduplicate
            var seen = new Set();
            return items.filter(i => {
                var key = i.text;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }""")
        print(f"[10] Layer tools bar: {len(layer_tools)}")
        for t in layer_tools:
            marker = ""
            lower = t['text'].lower()
            if any(kw in lower for kw in ['cloth', 'outfit', 'dress', 'fashion', 'wear', 'wardrobe', 'costume', 'change clothes']):
                marker = " *** CLOTHING ***"
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}' cls={t['cls']}{marker}")

        screenshot(page, "08_layer_tools_bar")

        # ============================================================
        # STEP 11: Try the Dzine website search / help
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 11: Search Dzine website for 'Change Clothes' feature")
        print(f"{'='*60}")

        search_page = context.new_page()
        search_page.set_viewport_size(VIEWPORT)
        try:
            search_page.goto("https://www.dzine.ai/", wait_until="domcontentloaded", timeout=15000)
            search_page.wait_for_timeout(3000)
            close_popups(search_page)

            # Search for clothing-related text on the main page
            main_page_clothes = search_page.evaluate("""() => {
                var text = document.body.innerText.toLowerCase();
                var matches = [];
                var keywords = ['change clothes', 'outfit', 'virtual try', 'wardrobe',
                               'clothing change', 'dress up', 'fashion'];
                for (var kw of keywords) {
                    var idx = text.indexOf(kw);
                    if (idx !== -1) {
                        matches.push({
                            keyword: kw,
                            context: text.substring(Math.max(0, idx - 30), idx + kw.length + 30)
                        });
                    }
                }
                return matches;
            }""")
            print(f"[11] Main page clothing mentions: {len(main_page_clothes)}")
            for m in main_page_clothes:
                print(f"  keyword='{m['keyword']}' context='...{m['context']}...'")

            # Check /features page
            search_page.goto("https://www.dzine.ai/features/", wait_until="domcontentloaded", timeout=10000)
            search_page.wait_for_timeout(2000)

            features_clothes = search_page.evaluate("""() => {
                var text = document.body.innerText.toLowerCase();
                var matches = [];
                var keywords = ['change clothes', 'outfit', 'virtual try', 'wardrobe',
                               'clothing', 'fashion', 'dress'];
                for (var kw of keywords) {
                    var idx = text.indexOf(kw);
                    if (idx !== -1) {
                        matches.push({
                            keyword: kw,
                            context: text.substring(Math.max(0, idx - 50), idx + kw.length + 50)
                        });
                    }
                }
                return matches;
            }""")
            print(f"[11b] Features page clothing mentions: {len(features_clothes)}")
            for m in features_clothes:
                print(f"  keyword='{m['keyword']}' context='...{m['context']}...'")

            screenshot(search_page, "09_features_page")

        except Exception as e:
            print(f"[11] Search error: {e}")
        finally:
            try:
                search_page.close(run_before_unload=False)
            except Exception:
                pass

        # ============================================================
        # STEP 12: Check API docs for clothing endpoints
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 12: Check Dzine API docs for clothing-related endpoints")
        print(f"{'='*60}")

        api_page = context.new_page()
        api_page.set_viewport_size(VIEWPORT)
        try:
            api_page.goto("https://www.dzine.ai/api/", wait_until="domcontentloaded", timeout=15000)
            api_page.wait_for_timeout(3000)
            close_popups(api_page)

            api_clothes = api_page.evaluate("""() => {
                var text = document.body.innerText;
                var lines = text.split('\\n').filter(l => l.trim().length > 0);
                var matches = [];
                var keywords = ['change clothes', 'outfit', 'virtual try', 'wardrobe',
                               'clothing', 'fashion', 'dress'];
                for (var line of lines) {
                    var lower = line.toLowerCase();
                    for (var kw of keywords) {
                        if (lower.includes(kw)) {
                            matches.push({keyword: kw, line: line.trim().substring(0, 120)});
                        }
                    }
                }
                return matches;
            }""")
            print(f"[12] API docs clothing mentions: {len(api_clothes)}")
            for m in api_clothes:
                print(f"  keyword='{m['keyword']}' line='{m['line']}'")

            # Also dump all API endpoint names
            api_endpoints = api_page.evaluate("""() => {
                var endpoints = [];
                for (var el of document.querySelectorAll('h2, h3, h4, [class*="endpoint"], [class*="method"]')) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 80) {
                        endpoints.push(text);
                    }
                }
                return [...new Set(endpoints)];
            }""")
            print(f"\n[12b] API endpoint names: {len(api_endpoints)}")
            for ep in api_endpoints:
                marker = " ***" if any(kw in ep.lower() for kw in ['cloth', 'outfit', 'dress', 'fashion', 'wear']) else ""
                print(f"  {ep}{marker}")

            screenshot(api_page, "10_api_docs")

        except Exception as e:
            print(f"[12] API docs error: {e}")
        finally:
            try:
                api_page.close(run_before_unload=False)
            except Exception:
                pass

        # ============================================================
        # STEP 13: Try the Image Editor's Local Edit with clothing prompt
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 13: Check if Local Edit can change clothes (mask + prompt)")
        print(f"{'='*60}")

        page.bring_to_front()
        page.wait_for_timeout(500)
        close_popups(page)
        close_panels(page)
        page.wait_for_timeout(500)

        # Open Image Editor
        page.mouse.click(40, 197)  # Distant tool first
        page.wait_for_timeout(800)
        page.mouse.click(40, 698)  # Image Editor
        page.wait_for_timeout(2000)

        # Click Local Edit sub-tool
        local_edit_click = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.collapse-option, .subtool-item')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Local Edit')) {
                    el.click();
                    return text;
                }
            }
            return null;
        }""")
        print(f"[13a] Local Edit click: {local_edit_click}")
        page.wait_for_timeout(2000)

        # Read the Local Edit panel
        local_edit_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            return {
                text: panel.innerText,
                elements: []
            };
        }""")
        if local_edit_panel:
            print(f"[13b] Local Edit panel text:")
            for line in local_edit_panel['text'].split('\n'):
                line = line.strip()
                if line:
                    print(f"  {line}")

        screenshot(page, "11_local_edit_panel")

        # ============================================================
        # STEP 14: Comprehensive DOM search for hidden/new features
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 14: DOM-level search for clothing-related classes/attributes")
        print(f"{'='*60}")

        close_panels(page)
        page.wait_for_timeout(500)

        dom_search = page.evaluate("""() => {
            var matches = [];
            var allElements = document.querySelectorAll('*');
            for (var el of allElements) {
                var cls = (el.className || '').toString().toLowerCase();
                var id = (el.id || '').toLowerCase();
                var text = (el.innerText || '').trim().toLowerCase();
                var attrs = '';
                for (var attr of el.attributes) {
                    attrs += attr.name + '=' + attr.value + ' ';
                }
                attrs = attrs.toLowerCase();

                if (cls.includes('cloth') || cls.includes('outfit') || cls.includes('wardrobe') ||
                    cls.includes('dress-up') || cls.includes('fashion') || cls.includes('try-on') ||
                    id.includes('cloth') || id.includes('outfit') || id.includes('wardrobe') ||
                    attrs.includes('cloth') || attrs.includes('outfit') || attrs.includes('wardrobe') ||
                    attrs.includes('change-clothes') || attrs.includes('try-on')) {
                    var r = el.getBoundingClientRect();
                    matches.push({
                        tag: el.tagName,
                        cls: (el.className || '').toString().substring(0, 80),
                        id: el.id || '',
                        text: text.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return matches;
        }""")
        print(f"[14] DOM clothing-related elements: {len(dom_search)}")
        for m in dom_search:
            print(f"  <{m['tag']}> cls='{m['cls']}' id='{m['id']}' text='{m['text']}' ({m['x']},{m['y']}) {m['w']}x{m['h']}")

        # ============================================================
        # STEP 15: Check web for Dzine "Change Clothes" feature info
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 15: Web search context — what does Dzine offer for clothing?")
        print(f"{'='*60}")

        # Open Google search in new tab
        google_page = context.new_page()
        google_page.set_viewport_size(VIEWPORT)
        try:
            google_page.goto(
                "https://www.google.com/search?q=dzine.ai+change+clothes+tool+feature",
                wait_until="domcontentloaded", timeout=15000
            )
            google_page.wait_for_timeout(3000)

            search_results = google_page.evaluate("""() => {
                var results = [];
                for (var el of document.querySelectorAll('h3')) {
                    var parent = el.closest('a');
                    var href = parent ? parent.href : '';
                    results.push({
                        title: el.innerText.trim(),
                        url: href
                    });
                }
                return results.slice(0, 10);
            }""")
            print(f"[15] Google results for 'dzine.ai change clothes':")
            for r in search_results:
                print(f"  '{r['title']}' -> {r['url']}")

            screenshot(google_page, "12_google_search")

        except Exception as e:
            print(f"[15] Google search error: {e}")
        finally:
            try:
                google_page.close(run_before_unload=False)
            except Exception:
                pass

        # ============================================================
        # FINAL SUMMARY
        # ============================================================
        print(f"\n{'='*70}")
        print("PHASE 157 — FINAL SUMMARY")
        print(f"{'='*70}")
        print(f"Screenshots saved to: {OUT_DIR}")
        print(f"Files:")
        for f in sorted(OUT_DIR.iterdir()):
            print(f"  {f.name}")

    except Exception as e:
        print(f"[P157] FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
