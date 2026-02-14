#!/usr/bin/env python3
"""Dzine Deep Exploration Part 8 — End-to-end Txt2Img test + Layers panel.

Tests:
1. Txt2Img Fast generation (2 credits) — prompt, generate, poll, extract URL
2. Layers panel mapping — layer list, controls, interactions
3. CC Generate workflow — select Ray, fill prompt, verify panel state
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


def count_results(page):
    """Count result images in the results panel."""
    return page.evaluate("""() => {
        return document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]').length;
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 8 — Generation Test + Layers")
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
    # TASK 1: Txt2Img Fast Generation Test (2 credits)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Txt2Img Fast Generation Test")
    print("=" * 70)

    # Count results before generation
    before_count = count_results(page)
    print(f"  Results before: {before_count}")

    # Open Txt2Img panel
    text = click_sidebar(page, 197, "Txt2Img")

    # Select Fast mode (2 credits — cheapest)
    fast_select = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };
        for (var btn of panel.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Fast') {
                btn.click();
                return { found: true };
            }
        }
        return { found: false };
    }""")
    print(f"  Fast mode selected: {json.dumps(fast_select)}")
    page.wait_for_timeout(500)

    # Fill prompt
    test_prompt = "Professional product photograph of premium wireless headphones on a clean white background. Studio lighting, sharp focus, commercial grade photography. No text, no watermarks."

    # Click textarea and type prompt
    prompt_fill = page.evaluate("""(prompt) => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };
        var ta = panel.querySelector('textarea');
        if (!ta) return { found: false, reason: 'no textarea' };

        // Focus and clear
        ta.focus();
        ta.value = '';

        // Use native input event
        ta.value = prompt;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));

        return { found: true, length: ta.value.length };
    }""", test_prompt)
    print(f"  Prompt fill: {json.dumps(prompt_fill)}")
    page.wait_for_timeout(500)

    # Verify prompt is set
    current_prompt = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var ta = panel.querySelector('textarea');
        return ta ? ta.value : '';
    }""")
    print(f"  Current prompt ({len(current_prompt)} chars): '{current_prompt[:80]}...'")

    # Check generate button state
    gen_state = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };
        var btn = panel.querySelector('.generative, #txt2img-generate-btn');
        if (!btn) return { found: false };
        var className = (typeof btn.className === 'string') ? btn.className : (btn.getAttribute('class') || '');
        return {
            found: true,
            text: (btn.innerText || '').trim(),
            disabled: btn.disabled || false,
            ready: className.includes('ready'),
            class: className.substring(0, 80)
        };
    }""")
    print(f"  Generate button: {json.dumps(gen_state)}")
    screenshot(page, "p173_before_generate")

    # Click generate if ready
    if gen_state.get("ready"):
        print("\n  GENERATING... (Fast mode, 2 credits)")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var btn = panel.querySelector('.generative.ready, #txt2img-generate-btn');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }""")

        # Poll for completion
        start_time = time.time()
        last_progress = ""
        while time.time() - start_time < 120:
            page.wait_for_timeout(3000)

            # Check for progress percentage
            progress = page.evaluate("""() => {
                var body = document.body.innerText;
                var match = body.match(/(\\d{1,3})%/);
                return match ? match[1] + '%' : '';
            }""")
            if progress and progress != last_progress:
                print(f"    Progress: {progress} ({int(time.time() - start_time)}s)")
                last_progress = progress

            # Check result count
            current_count = count_results(page)
            if current_count > before_count:
                elapsed = int(time.time() - start_time)
                print(f"  GENERATION COMPLETE! {elapsed}s, new results: {current_count - before_count}")
                break
        else:
            print(f"  TIMEOUT after 120s. Results: {count_results(page)}")

        screenshot(page, "p173_after_generate")

        # Extract result URLs
        result_urls = page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            var urls = [];
            for (var img of imgs) {
                urls.push(img.src.substring(0, 200));
            }
            return urls;
        }""")
        print(f"  Result URLs ({len(result_urls)}):")
        for url in result_urls[-4:]:  # Show last 4 (newest)
            print(f"    {url}")
    else:
        print("  Generate button not ready — skipping generation")

    # ================================================================
    # TASK 2: Layers Panel Mapping
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Layers Panel")
    print("=" * 70)

    # Click Layers tab
    layers_click = page.evaluate("""() => {
        for (var el of document.querySelectorAll('.header-item')) {
            if ((el.innerText || '').includes('Layer')) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Layers tab clicked: {layers_click}")
    page.wait_for_timeout(1000)

    # Map the layers panel
    layers_info = page.evaluate("""() => {
        // Find layers panel
        var layerPanel = document.querySelector('.layer-panel, [class*="layer-panel"], [class*="layers-panel"]');
        if (!layerPanel) {
            // Try to find by right side panel content
            for (var el of document.querySelectorAll('[class*="panel"]')) {
                if ((el.innerText || '').includes('Layer') && el.getBoundingClientRect().x > 800) {
                    layerPanel = el;
                    break;
                }
            }
        }

        // Get all layer items
        var layers = [];
        var layerItems = document.querySelectorAll('[class*="layer-item"], [class*="layer-row"]');
        for (var item of layerItems) {
            var rect = item.getBoundingClientRect();
            if (rect.height > 0) {
                var className = (typeof item.className === 'string') ? item.className : (item.getAttribute('class') || '');
                layers.push({
                    text: (item.innerText || '').trim().substring(0, 60),
                    class: className.substring(0, 80),
                    selected: className.includes('selected') || className.includes('active'),
                    pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                });
            }
        }

        // Find layer control buttons
        var controls = [];
        var rightPanel = document.querySelector('[class*="right-panel"], .header-item.layers');
        if (rightPanel) {
            for (var btn of rightPanel.parentElement.querySelectorAll('button')) {
                var rect = btn.getBoundingClientRect();
                if (rect.x > 1000 && rect.height > 0 && rect.height < 40) {
                    var className = (typeof btn.className === 'string') ? btn.className : (btn.getAttribute('class') || '');
                    controls.push({
                        text: (btn.innerText || '').trim().substring(0, 30),
                        class: className.substring(0, 60),
                        pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                    });
                }
            }
        }

        // Right panel text
        var rightText = '';
        for (var el of document.querySelectorAll('[class*="panel"]')) {
            var r = el.getBoundingClientRect();
            if (r.x > 1000 && r.width > 100 && r.height > 300) {
                rightText = el.innerText.substring(0, 800);
                break;
            }
        }

        return {
            layerPanel: !!layerPanel,
            layers: layers,
            controls: controls,
            rightText: rightText
        };
    }""")
    print(f"  Layer panel found: {layers_info['layerPanel']}")
    print(f"  Layers ({len(layers_info['layers'])}):")
    for layer in layers_info['layers']:
        sel = " [SELECTED]" if layer['selected'] else ""
        print(f"    '{layer['text'][:40]}' .{layer['class'][:30]} at ({layer['pos']['x']},{layer['pos']['y']}) {layer['pos']['w']}x{layer['pos']['h']}{sel}")
    print(f"  Controls ({len(layers_info['controls'])}):")
    for ctrl in layers_info['controls']:
        print(f"    '{ctrl['text']}' .{ctrl['class'][:40]} at ({ctrl['pos']['x']},{ctrl['pos']['y']})")
    if layers_info['rightText']:
        print(f"  Right panel text:")
        for line in layers_info['rightText'].split("\n")[:15]:
            if line.strip():
                print(f"    {line.strip()}")

    screenshot(page, "p173_layers_panel")

    # ================================================================
    # TASK 3: CC Generate — Select Ray and verify panel
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: CC Generate — Select Ray Character")
    print("=" * 70)

    # Open Character panel and click Generate Images
    text = click_sidebar(page, 306, "Character")

    # Click Generate Images collapse-option
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
        if (!panel) return false;
        for (var opt of panel.querySelectorAll('.collapse-option')) {
            if ((opt.innerText || '').includes('Generate Images')) {
                opt.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(3000)

    # Check if sub-panel opened (should have more elements now)
    cc_panel = get_panel_text(page)
    print(f"  Panel text after click:")
    for line in cc_panel.split("\n")[:20]:
        if line.strip():
            print(f"    {line.strip()}")

    # If panel didn't change, try double-clicking
    if "Walk" not in cc_panel and "Scene" not in cc_panel:
        print("  Sub-panel didn't open. Trying double-click...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
            if (!panel) return false;
            for (var opt of panel.querySelectorAll('.collapse-option')) {
                if ((opt.innerText || '').includes('Generate Images')) {
                    opt.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(3000)
        cc_panel = get_panel_text(page)
        print(f"  Panel after second click:")
        for line in cc_panel.split("\n")[:20]:
            if line.strip():
                print(f"    {line.strip()}")

    screenshot(page, "p173_cc_panel")

    # Select Ray character via hidden DOM
    ray_select = page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (!list) return { found: false, reason: 'no .c-character-list' };

        var items = list.querySelectorAll('.item, button, div');
        for (var item of items) {
            var txt = (item.innerText || '').trim();
            if (txt === 'Ray') {
                item.click();
                return { found: true, text: txt };
            }
        }
        return { found: false, reason: 'no Ray in list' };
    }""")
    print(f"\n  Ray selection: {json.dumps(ray_select)}")
    page.wait_for_timeout(2000)

    # Check panel state after Ray selection
    cc_after = get_panel_text(page)
    print(f"  Panel after Ray selection:")
    for line in cc_after.split("\n")[:25]:
        if line.strip():
            print(f"    {line.strip()}")

    screenshot(page, "p173_cc_ray_selected")

    # Map all interactive elements in the CC panel now
    cc_elements = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var results = [];
        var allEls = panel.querySelectorAll('input, textarea, button, .c-switch, .c-slider, .pick-image, [contenteditable="true"]');
        for (var el of allEls) {
            var rect = el.getBoundingClientRect();
            if (rect.height === 0) continue;
            var className = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
            results.push({
                tag: el.tagName,
                class: className.substring(0, 80),
                placeholder: (el.placeholder || '').substring(0, 80),
                text: (el.innerText || '').substring(0, 80),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
            });
        }
        return results;
    }""")
    print(f"\n  CC Panel elements ({len(cc_elements)}):")
    for el in cc_elements[:25]:
        info = el.get('placeholder', '') or el.get('text', '')[:50]
        print(f"    {el['tag']}.{el['class'][:40]} at ({el['pos']['x']},{el['pos']['y']}) {el['pos']['w']}x{el['pos']['h']} — '{info}'")

    # ================================================================
    # TASK 4: Check CC panel — @mention system
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: CC Panel — @Mention and Description System")
    print("=" * 70)

    # Look for character description (auto-populated)
    description = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false };

        // Find textarea or contenteditable with pre-filled content
        var textareas = panel.querySelectorAll('textarea, [contenteditable="true"]');
        var results = [];
        for (var ta of textareas) {
            var content = ta.value || ta.innerText || '';
            if (content.length > 10) {
                var rect = ta.getBoundingClientRect();
                results.push({
                    content: content.substring(0, 300),
                    length: content.length,
                    tag: ta.tagName,
                    pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                });
            }
        }
        return { found: results.length > 0, textareas: results };
    }""")
    print(f"  Pre-filled content: {json.dumps(description, indent=2)}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 8 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
