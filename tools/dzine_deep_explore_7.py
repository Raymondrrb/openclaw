#!/usr/bin/env python3
"""Dzine Deep Exploration Part 7 — Product Background hunt, Character CC details, Enhance popup.

Focus areas:
1. Product Background — check BG Remove action bar, canvas right-click, web tool
2. Character panel — Build/Manage/Insert/Sheet/360 sub-panels
3. Enhance & Upscale — popup from Results panel
4. Canvas top action bar — all buttons and tools
"""

import json
import sys
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def get_panel_text(page):
    return page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (p) return p.innerText.substring(0, 2000);
        p = document.querySelector('.panels.show');
        if (p) return p.innerText.substring(0, 2000);
        return 'NO PANEL';
    }""")


def click_sidebar(page, y, label="tool"):
    distant_y = 766 if abs(y - 766) > 100 else 81
    page.mouse.click(40, distant_y)
    page.wait_for_timeout(1500)
    page.mouse.click(40, y)
    page.wait_for_timeout(2500)
    text = get_panel_text(page)
    first_line = text.split("\n")[0] if text != "NO PANEL" else "NO PANEL"
    print(f"  [{label}] Panel starts with: {first_line}")
    return text


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 7")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    current = page.url
    print(f"Connected to Brave. Current URL: {current}")

    if "dzine.ai/canvas" not in current:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0:
                    btn.first.click(timeout=1000)
                    page.wait_for_timeout(500)
            except:
                pass

    # ================================================================
    # TASK 1: Map the canvas TOP action bar
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Canvas Top Action Bar (BG Remove location)")
    print("=" * 70)

    # First, select a layer on canvas (needed for action bar to show)
    # Click canvas center to select any layer
    page.mouse.click(720, 450)
    page.wait_for_timeout(1000)

    # Map all buttons in the action bar area (y ~ 57-110)
    action_bar = page.evaluate("""() => {
        var results = [];
        // Check for action bar buttons between y=50 and y=120
        var allBtns = document.querySelectorAll('button, [role="button"]');
        for (var btn of allBtns) {
            var rect = btn.getBoundingClientRect();
            if (rect.y > 50 && rect.y < 120 && rect.height > 0 && rect.height < 40 && rect.x > 80) {
                var className = (typeof btn.className === 'string') ? btn.className : (btn.getAttribute('class') || '');
                results.push({
                    text: (btn.innerText || '').trim().substring(0, 40),
                    class: className.substring(0, 80),
                    pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                });
            }
        }

        // Also check for any floating toolbar
        var toolbar = document.querySelector('[class*="action-bar"], [class*="toolbar"], [class*="layer-tool"]');
        var toolbarInfo = null;
        if (toolbar) {
            var rect = toolbar.getBoundingClientRect();
            toolbarInfo = {
                class: (typeof toolbar.className === 'string') ? toolbar.className : (toolbar.getAttribute('class') || ''),
                text: toolbar.innerText.substring(0, 500),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
            };
        }

        return { buttons: results, toolbar: toolbarInfo };
    }""")
    print(f"  Action bar buttons ({len(action_bar['buttons'])}):")
    for b in action_bar['buttons']:
        print(f"    '{b['text']}' .{b['class'][:40]} at ({b['pos']['x']},{b['pos']['y']}) {b['pos']['w']}x{b['pos']['h']}")
    if action_bar['toolbar']:
        print(f"  Toolbar: .{action_bar['toolbar']['class'][:60]}")
        print(f"    Text: {action_bar['toolbar']['text'][:200]}")

    # Search for BG Remove anywhere on the page
    bg_remove = page.evaluate("""() => {
        var found = [];
        for (var el of document.querySelectorAll('*')) {
            var txt = (el.innerText || '').trim();
            if (txt.includes('BG Remove') || txt.includes('Background') && txt.length < 50) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0 && rect.height < 50 && rect.x > 0) {
                    var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
                    found.push({
                        text: txt.substring(0, 60),
                        tag: el.tagName,
                        class: className.substring(0, 60),
                        pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                    });
                }
            }
        }
        return found;
    }""")
    print(f"\n  BG Remove / Background elements ({len(bg_remove)}):")
    for el in bg_remove[:15]:
        print(f"    '{el['text']}' <{el['tag']}>.{el['class'][:30]} at ({el['pos']['x']},{el['pos']['y']}) {el['pos']['w']}x{el['pos']['h']}")

    screenshot(page, "p172_action_bar")

    # ================================================================
    # TASK 2: Search for Product Background as a separate page/tool
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Product Background — search page body text")
    print("=" * 70)

    # Check if there's a "Product Background" or "Product BG" text anywhere
    product_bg = page.evaluate("""() => {
        var body = document.body.innerText;
        var matches = [];
        var lines = body.split('\\n');
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (line.toLowerCase().includes('product') && line.toLowerCase().includes('background')) {
                matches.push(line.substring(0, 100));
            }
        }
        return { matches: matches, bodyLength: body.length };
    }""")
    print(f"  'Product Background' text matches: {json.dumps(product_bg)}")

    # ================================================================
    # TASK 3: Character Panel — map sub-features
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Character Panel — Sub-feature Details")
    print("=" * 70)

    text = click_sidebar(page, 306, "Character")
    screenshot(page, "p172_character_panel")

    # Map the Character panel overview
    char_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) {
            panel = document.querySelector('.panels.show');
        }
        if (!panel) return { found: false };

        var rect = panel.getBoundingClientRect();

        // Find all collapse-options
        var options = [];
        for (var opt of panel.querySelectorAll('.collapse-option, [class*="collapse-option"]')) {
            var name = (opt.innerText || '').trim();
            var r = opt.getBoundingClientRect();
            var className = (typeof opt.className === 'string') ? opt.className : (opt.getAttribute('class') || '');
            options.push({
                text: name.split('\\n')[0],
                fullText: name.substring(0, 100),
                class: className.substring(0, 80),
                pos: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
            });
        }

        // Find buttons
        var buttons = [];
        for (var btn of panel.querySelectorAll('button')) {
            var txt = (btn.innerText || '').trim();
            if (txt && txt.length < 50) {
                var r = btn.getBoundingClientRect();
                if (r.height > 0) {
                    var className = (typeof btn.className === 'string') ? btn.className : (btn.getAttribute('class') || '');
                    buttons.push({
                        text: txt,
                        class: className.substring(0, 60),
                        pos: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
                    });
                }
            }
        }

        return {
            found: true,
            panelClass: (typeof panel.className === 'string') ? panel.className : '',
            pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
            text: panel.innerText.substring(0, 1500),
            options: options,
            buttons: buttons.slice(0, 20)
        };
    }""")
    print(f"  Panel class: {char_panel.get('panelClass', 'N/A')[:60]}")
    print(f"  Options ({len(char_panel.get('options', []))}):")
    for opt in char_panel.get('options', []):
        print(f"    '{opt['text']}' — {opt['fullText'][:80]} at ({opt['pos']['x']},{opt['pos']['y']})")
    print(f"  Buttons ({len(char_panel.get('buttons', []))}):")
    for btn in char_panel.get('buttons', [])[:10]:
        print(f"    '{btn['text']}' .{btn['class'][:40]} at ({btn['pos']['x']},{btn['pos']['y']})")

    # Now click "Generate Images" to open the CC sub-panel
    print("\n  [3a] Opening CC Generate Images sub-panel...")
    cc_open = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
        if (!panel) return { found: false, reason: 'no panel' };

        for (var opt of panel.querySelectorAll('.collapse-option, [class*="collapse-option"], p, div')) {
            var txt = (opt.innerText || '').trim();
            if (txt.includes('Generate Images') && txt.includes('character')) {
                opt.click();
                return { found: true, text: txt.substring(0, 80) };
            }
        }
        // Try button approach
        for (var el of panel.querySelectorAll('*')) {
            var txt = (el.innerText || '').trim();
            if (txt === 'Generate Images' || (txt.includes('Generate Images') && txt.length < 60)) {
                var r = el.getBoundingClientRect();
                if (r.height > 20 && r.height < 80) {
                    el.click();
                    return { found: true, text: txt.substring(0, 80), tag: el.tagName };
                }
            }
        }
        return { found: false, reason: 'no Generate Images option' };
    }""")
    print(f"  CC open: {json.dumps(cc_open)}")
    page.wait_for_timeout(2500)

    # Map the CC Generate panel in detail
    cc_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };

        // Map all interactive elements
        var elements = [];
        var allEls = panel.querySelectorAll('input, textarea, button, .c-switch, .c-slider, .pick-image, select, [contenteditable], [role="button"]');
        for (var el of allEls) {
            var rect = el.getBoundingClientRect();
            if (rect.height === 0) continue;
            var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
            elements.push({
                tag: el.tagName,
                class: className.substring(0, 80),
                placeholder: (el.placeholder || '').substring(0, 100),
                text: (el.innerText || '').substring(0, 80),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
            });
        }

        return {
            found: true,
            text: panel.innerText.substring(0, 2000),
            elements: elements
        };
    }""")
    if cc_panel.get("found"):
        print(f"\n  CC Generate panel elements ({len(cc_panel['elements'])}):")
        for el in cc_panel['elements'][:25]:
            print(f"    {el['tag']}.{el['class'][:40]} at ({el['pos']['x']},{el['pos']['y']}) {el['pos']['w']}x{el['pos']['h']} — '{el.get('placeholder','') or el.get('text','')[:50]}'")

        # Print panel text organized
        print(f"\n  CC Panel full text:")
        for line in cc_panel['text'].split("\n")[:40]:
            if line.strip():
                print(f"    {line.strip()}")

        screenshot(page, "p172_cc_generate")

    # ================================================================
    # TASK 4: CC — Character Selection and Quick Actions
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: CC — Character List and Quick Actions")
    print("=" * 70)

    # Check for character list
    char_list = page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (!list) return { found: false, reason: 'no .c-character-list' };

        var rect = list.getBoundingClientRect();
        var items = [];
        for (var item of list.querySelectorAll('.item, button, div')) {
            var txt = (item.innerText || '').trim();
            if (txt && txt.length < 30 && !txt.includes('\\n')) {
                var r = item.getBoundingClientRect();
                items.push({ name: txt, pos: { x: Math.round(r.x), y: Math.round(r.y) } });
            }
        }

        return {
            found: true,
            visible: rect.width > 0 && rect.height > 0,
            pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
            items: items
        };
    }""")
    print(f"  Character list: {json.dumps(char_list)}")

    # Look for Quick Actions
    quick_actions = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];

        var actions = [];
        for (var el of panel.querySelectorAll('button, [class*="action"], [class*="quick"]')) {
            var txt = (el.innerText || '').trim();
            if (['Walk', 'Read', 'Wave', 'Sit', 'Run', 'Stand'].some(a => txt.includes(a))) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0) {
                    actions.push({
                        text: txt,
                        pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                    });
                }
            }
        }
        return actions;
    }""")
    print(f"  Quick Actions: {json.dumps(quick_actions)}")

    # Check for Control Mode (Camera/Pose/Reference)
    control_mode = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];

        var modes = [];
        for (var el of panel.querySelectorAll('button, [class*="mode"], [class*="option"]')) {
            var txt = (el.innerText || '').trim();
            if (['Camera', 'Pose', 'Reference'].includes(txt)) {
                var rect = el.getBoundingClientRect();
                var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
                if (rect.height > 0) {
                    modes.push({
                        text: txt,
                        selected: className.includes('selected') || className.includes('active'),
                        pos: { x: Math.round(rect.x), y: Math.round(rect.y) }
                    });
                }
            }
        }
        return modes;
    }""")
    print(f"  Control modes: {json.dumps(control_mode)}")

    # ================================================================
    # TASK 5: Character — Insert Character sub-panel
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Character — Insert Character sub-panel")
    print("=" * 70)

    # Go back to Character overview
    text = click_sidebar(page, 306, "Character-return")

    # Click Insert Character
    insert_open = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
        if (!panel) return { found: false, reason: 'no panel' };

        for (var el of panel.querySelectorAll('*')) {
            var txt = (el.innerText || '').trim();
            if (txt.includes('Insert Character') && txt.includes('Into')) {
                var r = el.getBoundingClientRect();
                if (r.height > 20 && r.height < 80) {
                    el.click();
                    return { found: true, text: txt.substring(0, 80) };
                }
            }
        }
        return { found: false, reason: 'no Insert Character option' };
    }""")
    print(f"  Insert Character: {json.dumps(insert_open)}")
    page.wait_for_timeout(2500)

    # Map the Insert Character panel
    insert_panel_text = get_panel_text(page)
    print(f"  Panel text:")
    for line in insert_panel_text.split("\n")[:30]:
        if line.strip():
            print(f"    {line.strip()}")
    screenshot(page, "p172_insert_character")

    # ================================================================
    # TASK 6: Character — Character Sheet sub-panel
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 6: Character — Character Sheet sub-panel")
    print("=" * 70)

    text = click_sidebar(page, 306, "Character-return2")

    sheet_open = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
        if (!panel) return { found: false };

        for (var el of panel.querySelectorAll('*')) {
            var txt = (el.innerText || '').trim();
            if (txt.includes('Character Sheet') && txt.includes('From prompt')) {
                var r = el.getBoundingClientRect();
                if (r.height > 20 && r.height < 80) {
                    el.click();
                    return { found: true, text: txt.substring(0, 80) };
                }
            }
        }
        return { found: false };
    }""")
    print(f"  Sheet open: {json.dumps(sheet_open)}")
    page.wait_for_timeout(2500)

    sheet_text = get_panel_text(page)
    print(f"  Panel text:")
    for line in sheet_text.split("\n")[:30]:
        if line.strip():
            print(f"    {line.strip()}")
    screenshot(page, "p172_character_sheet")

    # ================================================================
    # TASK 7: Character — Build Your Character
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 7: Character — Build Your Character dialog")
    print("=" * 70)

    text = click_sidebar(page, 306, "Character-return3")

    build_open = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
        if (!panel) return { found: false };

        for (var btn of panel.querySelectorAll('button')) {
            var txt = (btn.innerText || '').trim();
            if (txt.includes('Build Your Character')) {
                btn.click();
                return { found: true, text: txt };
            }
        }
        return { found: false };
    }""")
    print(f"  Build open: {json.dumps(build_open)}")
    page.wait_for_timeout(3000)

    # Check for dialog
    dialog = page.evaluate("""() => {
        // Look for any dialog/modal
        for (var el of document.querySelectorAll('[class*="modal"], [class*="dialog"], [class*="popup"], [role="dialog"]')) {
            var rect = el.getBoundingClientRect();
            if (rect.width > 200 && rect.height > 200) {
                return {
                    found: true,
                    class: (typeof el.className === 'string') ? el.className.substring(0, 100) : '',
                    text: el.innerText.substring(0, 1500),
                    pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                };
            }
        }

        // Also check for full-page overlay
        var overlay = document.querySelector('[class*="overlay"], [class*="character-create"]');
        if (overlay) {
            var rect = overlay.getBoundingClientRect();
            if (rect.width > 200) {
                return {
                    found: true,
                    isOverlay: true,
                    class: (typeof overlay.className === 'string') ? overlay.className.substring(0, 100) : '',
                    text: overlay.innerText.substring(0, 1500)
                };
            }
        }

        // Check body for new content
        var body = document.body.innerText;
        if (body.includes('Start with') || body.includes('Upload') || body.includes('character name')) {
            return { found: true, source: 'body', snippet: body.substring(0, 500) };
        }

        return { found: false };
    }""")
    print(f"  Dialog: {json.dumps(dialog)}")
    screenshot(page, "p172_build_character")

    # Close dialog if open
    page.keyboard.press("Escape")
    page.wait_for_timeout(1000)

    # ================================================================
    # TASK 8: Assets panel
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 8: Assets Panel")
    print("=" * 70)

    text = click_sidebar(page, 136, "Assets")
    print(f"  Panel text:")
    for line in text.split("\n")[:20]:
        if line.strip():
            print(f"    {line.strip()}")
    screenshot(page, "p172_assets_panel")

    # ================================================================
    # TASK 9: Right-click canvas context menu
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 9: Canvas Right-Click Context Menu")
    print("=" * 70)

    # Close current panel
    page.mouse.click(40, 81)  # Click Upload
    page.wait_for_timeout(1000)

    # Right-click on canvas
    page.mouse.click(720, 450, button="right")
    page.wait_for_timeout(1500)

    context_menu = page.evaluate("""() => {
        // Look for context menu
        for (var el of document.querySelectorAll('[class*="context-menu"], [class*="dropdown-menu"], [class*="popover"], .menu')) {
            var rect = el.getBoundingClientRect();
            if (rect.width > 50 && rect.height > 50) {
                return {
                    found: true,
                    class: (typeof el.className === 'string') ? el.className.substring(0, 80) : '',
                    text: el.innerText.substring(0, 500),
                    pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                };
            }
        }
        return { found: false };
    }""")
    print(f"  Context menu: {json.dumps(context_menu)}")
    if context_menu.get("found"):
        screenshot(page, "p172_context_menu")

    # Close context menu
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    print("\n" + "=" * 70)
    print("EXPLORATION PART 7 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
