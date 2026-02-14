#!/usr/bin/env python3
"""Dzine Deep Exploration Part 6 — Txt2Img Advanced, Img2Img Advanced, Product Background.

Uses panel toggle technique (click distant tool first) to reliably switch panels.
SVG className bug fixed: uses getAttribute('class') instead of .className.
"""

import json
import sys
import time
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def safe_text(el_text):
    """Truncate for display."""
    return (el_text or "")[:500]


def get_panel_text(page):
    """Get text of currently active panel."""
    return page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (p) return p.innerText.substring(0, 2000);
        p = document.querySelector('.panels.show');
        if (p) return p.innerText.substring(0, 2000);
        return 'NO PANEL';
    }""")


def click_sidebar(page, y, label="tool"):
    """Click sidebar at given y coordinate with toggle technique."""
    # First click a distant tool (Storyboard at 766 or Upload at 81)
    distant_y = 766 if abs(y - 766) > 100 else 81
    page.mouse.click(40, distant_y)
    page.wait_for_timeout(1500)
    page.mouse.click(40, y)
    page.wait_for_timeout(2500)
    text = get_panel_text(page)
    first_line = text.split("\n")[0] if text != "NO PANEL" else "NO PANEL"
    print(f"  [{label}] Panel starts with: {first_line}")
    return text


def map_advanced_section(page, panel_name):
    """Click Advanced button and map all elements inside."""
    result = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false, reason: 'no panel' };

        // Find Advanced button
        var advBtn = null;
        for (var btn of panel.querySelectorAll('button, .advanced-btn, [class*="advanced"]')) {
            var txt = (btn.innerText || '').trim().toLowerCase();
            if (txt.includes('advanced')) { advBtn = btn; break; }
        }
        if (!advBtn) return { found: false, reason: 'no Advanced button' };

        // Check if already expanded
        var rect = advBtn.getBoundingClientRect();
        advBtn.click();

        return {
            found: true,
            btnClass: (typeof advBtn.className === 'string') ? advBtn.className : (advBtn.getAttribute('class') || ''),
            btnPos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
        };
    }""")
    print(f"  Advanced button: {json.dumps(result)}")
    page.wait_for_timeout(1500)

    if not result.get("found"):
        return result

    # Now map everything in the advanced section
    advanced = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { error: 'no panel' };

        var elements = [];
        // Look for inputs, textareas, sliders, switches, buttons in the panel
        var allEls = panel.querySelectorAll('input, textarea, .c-switch, .c-slider, button, select, [role="slider"]');
        for (var el of allEls) {
            var rect = el.getBoundingClientRect();
            if (rect.height === 0 || rect.y < 0) continue;
            var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
            elements.push({
                tag: el.tagName,
                type: el.type || '',
                class: className.substring(0, 100),
                placeholder: (el.placeholder || '').substring(0, 100),
                value: (el.value || '').substring(0, 50),
                text: (el.innerText || '').substring(0, 100),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
            });
        }

        // Get full panel text for context
        return {
            elements: elements,
            panelText: panel.innerText.substring(0, 3000)
        };
    }""")
    return advanced


def explore_product_background(page):
    """Scroll to and click Product Background in Image Editor."""
    # Open Image Editor
    text = click_sidebar(page, 698, "ImageEditor")
    if "NO PANEL" in text:
        print("  ERROR: Image Editor panel not opened")
        return None

    # Find and click Product Background / Background collapse-option
    result = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false, reason: 'no panel' };

        var options = panel.querySelectorAll('.collapse-option, [class*="collapse-option"]');
        var found = null;
        var allNames = [];
        for (var opt of options) {
            var name = (opt.innerText || '').trim().split('\\n')[0];
            allNames.push(name);
            if (name.toLowerCase().includes('background') || name.toLowerCase().includes('product bg')) {
                found = opt;
            }
        }

        if (!found) return { found: false, allOptions: allNames };

        // Scroll to it first
        found.scrollIntoView({ behavior: 'instant', block: 'center' });

        var rect = found.getBoundingClientRect();
        return {
            found: true,
            name: (found.innerText || '').trim().split('\\n')[0],
            pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
            allOptions: allNames
        };
    }""")
    print(f"  Product Background search: {json.dumps(result)}")

    if result.get("found"):
        page.wait_for_timeout(500)
        # Click it
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var options = panel.querySelectorAll('.collapse-option, [class*="collapse-option"]');
            for (var opt of options) {
                var name = (opt.innerText || '').trim().split('\\n')[0];
                if (name.toLowerCase().includes('background')) { opt.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

        # Map the sub-panel
        sub_text = get_panel_text(page)
        print(f"  Sub-panel text:\n{safe_text(sub_text)}")
        screenshot(page, "p171_product_background")

        # Map all interactive elements
        elements = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var results = [];
            var allEls = panel.querySelectorAll('input, textarea, button, .c-switch, .c-slider, .pick-image, .upload-image-btn, select, [role="slider"], [role="button"]');
            for (var el of allEls) {
                var rect = el.getBoundingClientRect();
                if (rect.height === 0) continue;
                var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
                results.push({
                    tag: el.tagName,
                    type: el.type || '',
                    class: className.substring(0, 120),
                    placeholder: (el.placeholder || '').substring(0, 100),
                    text: (el.innerText || '').substring(0, 150),
                    pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                });
            }
            return results;
        }""")
        print(f"  Interactive elements ({len(elements)}):")
        for el in elements[:30]:
            print(f"    {el['tag']}.{el['class'][:40]} at ({el['pos']['x']},{el['pos']['y']}) {el['pos']['w']}x{el['pos']['h']} — {el.get('placeholder','') or el.get('text','')[:60]}")

        return {"text": sub_text, "elements": elements}

    return result


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 6 — Txt2Img/Img2Img Advanced + Product BG")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]

    # Navigate to a canvas page
    current = page.url
    print(f"Connected to Brave. Current URL: {current}")

    if "dzine.ai/canvas" not in current:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)
        # Dismiss dialogs
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0:
                    btn.first.click(timeout=1000)
                    page.wait_for_timeout(500)
            except:
                pass

    # ================================================================
    # TASK 1: Txt2Img Advanced Section
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Txt2Img — Advanced Section (Seed, Negative Prompt)")
    print("=" * 70)

    text = click_sidebar(page, 197, "Txt2Img")
    screenshot(page, "p171_txt2img_panel")

    # Check toggles state
    toggles = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var switches = panel.querySelectorAll('.c-switch');
        var results = [];
        for (var sw of switches) {
            var rect = sw.getBoundingClientRect();
            if (rect.height === 0) continue;
            // Find nearest label
            var parent = sw.parentElement;
            var label = '';
            if (parent) {
                for (var child of parent.children) {
                    if (child !== sw && child.innerText) { label = child.innerText.trim(); break; }
                }
            }
            var className = (typeof sw.className === 'string') ? sw.className : (sw.getAttribute('class') || '');
            results.push({
                label: label,
                checked: className.includes('isChecked'),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y) }
            });
        }
        return results;
    }""")
    print(f"\n  Toggles ({len(toggles)}):")
    for t in toggles:
        state = "ON" if t['checked'] else "OFF"
        print(f"    {t['label']} = {state} at ({t['pos']['x']},{t['pos']['y']})")

    print("\n  [1a] Expanding Advanced section...")
    advanced = map_advanced_section(page, "Txt2Img")
    screenshot(page, "p171_txt2img_advanced")

    if isinstance(advanced, dict) and "elements" in advanced:
        print(f"\n  Advanced section elements ({len(advanced['elements'])}):")
        for el in advanced['elements'][:20]:
            print(f"    {el['tag']}.{el['class'][:40]} at ({el['pos']['x']},{el['pos']['y']}) {el['pos']['w']}x{el['pos']['h']} — ph:'{el.get('placeholder','')}' val:'{el.get('value','')[:30]}' txt:'{el.get('text','')[:40]}'")

        # Extract negative prompt if present
        print(f"\n  Full panel text (after Advanced expand):")
        panel_text = advanced.get("panelText", "")
        # Print line by line for readability
        for line in panel_text.split("\n")[:50]:
            if line.strip():
                print(f"    {line.strip()}")

    # ================================================================
    # TASK 2: Img2Img Advanced Section
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Img2Img — Advanced Section")
    print("=" * 70)

    text = click_sidebar(page, 252, "Img2Img")
    screenshot(page, "p171_img2img_panel")

    # Check toggles
    toggles2 = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var switches = panel.querySelectorAll('.c-switch');
        var results = [];
        for (var sw of switches) {
            var rect = sw.getBoundingClientRect();
            if (rect.height === 0) continue;
            var parent = sw.parentElement;
            var label = '';
            if (parent) {
                for (var child of parent.children) {
                    if (child !== sw && child.innerText) { label = child.innerText.trim(); break; }
                }
            }
            var className = (typeof sw.className === 'string') ? sw.className : (sw.getAttribute('class') || '');
            results.push({
                label: label,
                checked: className.includes('isChecked'),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y) }
            });
        }
        return results;
    }""")
    print(f"\n  Toggles ({len(toggles2)}):")
    for t in toggles2:
        state = "ON" if t['checked'] else "OFF"
        print(f"    {t['label']} = {state} at ({t['pos']['x']},{t['pos']['y']})")

    print("\n  [2a] Expanding Advanced section...")
    advanced2 = map_advanced_section(page, "Img2Img")
    screenshot(page, "p171_img2img_advanced")

    if isinstance(advanced2, dict) and "elements" in advanced2:
        print(f"\n  Advanced section elements ({len(advanced2['elements'])}):")
        for el in advanced2['elements'][:20]:
            print(f"    {el['tag']}.{el['class'][:40]} at ({el['pos']['x']},{el['pos']['y']}) {el['pos']['w']}x{el['pos']['h']} — ph:'{el.get('placeholder','')}' val:'{el.get('value','')[:30]}' txt:'{el.get('text','')[:40]}'")

        print(f"\n  Full panel text (after Advanced expand):")
        panel_text2 = advanced2.get("panelText", "")
        for line in panel_text2.split("\n")[:50]:
            if line.strip():
                print(f"    {line.strip()}")

    # ================================================================
    # TASK 3: Img2Img — Structure Match and Describe Canvas
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Img2Img — Structure Match Slider + Describe Canvas")
    print("=" * 70)

    # Map the structure match slider in detail
    slider = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };

        var slider = panel.querySelector('.c-slider');
        if (!slider) return { found: false, reason: 'no .c-slider' };

        var rect = slider.getBoundingClientRect();

        // Look for related labels
        var parent = slider.parentElement;
        var labels = [];
        if (parent) {
            var els = parent.querySelectorAll('*');
            for (var el of els) {
                if (el.innerText && el.children.length === 0) {
                    labels.push(el.innerText.trim());
                }
            }
        }

        // Look for the track and thumb
        var track = slider.querySelector('[class*="track"], [class*="rail"], [role="slider"]');
        var thumb = slider.querySelector('[class*="thumb"], [class*="handle"]');

        return {
            found: true,
            pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
            labels: labels,
            hasTrack: !!track,
            hasThumb: !!thumb,
            sliderHTML: slider.outerHTML.substring(0, 500)
        };
    }""")
    print(f"  Structure Match slider: {json.dumps(slider)}")

    # Map Describe Canvas button
    describe = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };

        var btn = panel.querySelector('.autoprompt, button.autoprompt');
        if (!btn) {
            // Search by text
            for (var b of panel.querySelectorAll('button')) {
                if ((b.innerText || '').includes('Describe')) { btn = b; break; }
            }
        }
        if (!btn) return { found: false, reason: 'no autoprompt button' };

        var rect = btn.getBoundingClientRect();
        var className = (typeof btn.className === 'string') ? btn.className : (btn.getAttribute('class') || '');
        return {
            found: true,
            class: className,
            text: (btn.innerText || '').trim(),
            visible: btn.offsetHeight > 0,
            pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
        };
    }""")
    print(f"  Describe Canvas button: {json.dumps(describe)}")

    # ================================================================
    # TASK 4: Product Background sub-tool
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Product Background sub-tool in Image Editor")
    print("=" * 70)

    bg_result = explore_product_background(page)

    # ================================================================
    # TASK 5: Quick Style + Style creation from Style Picker
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Style Picker — Quick/Pro Style Details")
    print("=" * 70)

    # Open Txt2Img to access style picker
    text = click_sidebar(page, 197, "Txt2Img")

    # Click style button
    style_result = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };
        var btn = panel.querySelector('button.style, .style-name');
        if (!btn) return { found: false, reason: 'no style button' };
        btn.click();
        return { found: true, text: (btn.innerText || '').trim() };
    }""")
    print(f"  Style button clicked: {json.dumps(style_result)}")
    page.wait_for_timeout(2000)

    # Map the style picker panel
    style_panel = page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel, [class*="style-list"]');
        if (!panel) return { found: false, reason: 'no style-list-panel' };

        var rect = panel.getBoundingClientRect();

        // Count styles
        var items = panel.querySelectorAll('[class*="style-item"]');

        // Find tabs/categories
        var tabs = [];
        var tabEls = panel.querySelectorAll('[class*="tab"], [class*="category"], .item');
        for (var t of tabEls) {
            var txt = (t.innerText || '').trim();
            if (txt && txt.length < 30 && !txt.includes('\\n')) tabs.push(txt);
        }

        // Find search input
        var search = panel.querySelector('input[type="text"]');

        // Find Quick Style / Pro Style buttons
        var quickStyle = null;
        var proStyle = null;
        for (var el of panel.querySelectorAll('*')) {
            var txt = (el.innerText || '').trim();
            if (txt === 'Quick Style' || txt.includes('Quick Style')) quickStyle = { text: txt, tag: el.tagName };
            if (txt === 'Pro Style' || txt === 'Train a Pro Style') proStyle = { text: txt, tag: el.tagName };
        }

        return {
            found: true,
            pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
            styleCount: items.length,
            categories: tabs.slice(0, 25),
            hasSearch: !!search,
            quickStyle: quickStyle,
            proStyle: proStyle,
            panelText: panel.innerText.substring(0, 1000)
        };
    }""")
    print(f"  Style picker: {json.dumps(style_panel)}")
    screenshot(page, "p171_style_picker")

    # Look for My Styles tab and Quick/Pro style creation
    my_styles = page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel, [class*="style-list"]');
        if (!panel) return { found: false };

        // Click "My Styles" tab if present
        for (var el of panel.querySelectorAll('*')) {
            var txt = (el.innerText || '').trim();
            if (txt === 'My Styles') { el.click(); return { found: true, clicked: 'My Styles' }; }
        }
        return { found: false, reason: 'no My Styles tab' };
    }""")
    print(f"  My Styles tab: {json.dumps(my_styles)}")
    page.wait_for_timeout(1500)

    if my_styles.get("found"):
        my_styles_content = page.evaluate("""() => {
            var panel = document.querySelector('.style-list-panel, [class*="style-list"]');
            if (!panel) return 'NO PANEL';
            return panel.innerText.substring(0, 1500);
        }""")
        print(f"  My Styles content:\n{safe_text(my_styles_content)}")
        screenshot(page, "p171_my_styles")

    # Close style picker by pressing Escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ================================================================
    # TASK 6: Map all generation mode options across tools
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 6: Txt2Img — Generation Mode Details")
    print("=" * 70)

    # Ensure Txt2Img panel is open
    text = click_sidebar(page, 197, "Txt2Img")

    gen_modes = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };

        var modes = [];
        // Look for Fast/Normal/HQ buttons
        for (var btn of panel.querySelectorAll('button')) {
            var txt = (btn.innerText || '').trim();
            if (['Fast', 'Normal', 'HQ'].includes(txt)) {
                var rect = btn.getBoundingClientRect();
                var className = (typeof btn.className === 'string') ? btn.className : (btn.getAttribute('class') || '');
                modes.push({
                    name: txt,
                    selected: className.includes('selected') || className.includes('active'),
                    class: className.substring(0, 80),
                    pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                });
            }
        }

        // Find Generate button for credit display
        var genBtn = panel.querySelector('.generative, #txt2img-generate-btn');
        var genInfo = null;
        if (genBtn) {
            var rect = genBtn.getBoundingClientRect();
            genInfo = {
                text: (genBtn.innerText || '').trim(),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y) }
            };
        }

        // Find aspect ratio buttons
        var ratios = [];
        var ratioContainer = panel.querySelector('.c-aspect-ratio');
        if (ratioContainer) {
            for (var btn of ratioContainer.querySelectorAll('button, .item')) {
                var txt = (btn.innerText || '').trim() || 'icon';
                var className = (typeof btn.className === 'string') ? btn.className : (btn.getAttribute('class') || '');
                ratios.push({
                    text: txt,
                    selected: className.includes('selected') || className.includes('active') || className.includes('canvas'),
                    class: className.substring(0, 60)
                });
            }
        }

        return {
            modes: modes,
            generate: genInfo,
            ratios: ratios
        };
    }""")
    print(f"  Generation modes: {json.dumps(gen_modes, indent=2)}")

    # ================================================================
    # TASK 7: Check credits display in header
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 7: Current Credit Balance")
    print("=" * 70)

    credits = page.evaluate("""() => {
        var header = document.querySelector('header, .header, [class*="header"]');
        var allText = document.body.innerText;

        // Look for credit display patterns
        var creditMatch = allText.match(/(\\d+[,.]\\d+)\\s*(?:credits?|video|image)/i);
        var unlimitedMatch = allText.match(/unlimited/i);

        // Find specific credit elements
        var creditEls = [];
        for (var el of document.querySelectorAll('span.txt, [class*="credit"], [class*="balance"]')) {
            var txt = (el.innerText || '').trim();
            if (txt && txt.length < 30) {
                creditEls.push({ text: txt, class: (typeof el.className === 'string') ? el.className.substring(0, 50) : '' });
            }
        }

        // Also check header bar specifically
        var headerBar = document.querySelector('.header-bar, header');
        var headerText = headerBar ? headerBar.innerText.substring(0, 300) : '';

        return {
            creditElements: creditEls,
            headerText: headerText,
            hasUnlimited: !!unlimitedMatch
        };
    }""")
    print(f"  Credits: {json.dumps(credits, indent=2)}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 6 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
