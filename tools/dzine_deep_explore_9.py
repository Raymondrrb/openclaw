#!/usr/bin/env python3
"""Dzine Deep Exploration Part 9 — Retry Txt2Img generation + layer interaction.

Fix: navigate away from Character sub-panel properly before opening Txt2Img.
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


def count_results(page):
    return page.evaluate("""() => {
        return document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]').length;
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 9 — Txt2Img Gen Test + Layer Interaction")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    current = page.url
    print(f"Connected to Brave. Current URL: {current}")

    if "dzine.ai/canvas" not in current:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # First, exit the CC sub-panel by clicking the back button
    print("\n  Exiting CC sub-panel...")
    page.evaluate("""() => {
        var back = document.querySelector('button.back');
        if (back) { back.click(); return 'clicked back'; }
        return 'no back button';
    }""")
    page.wait_for_timeout(1000)

    # ================================================================
    # TASK 1: Txt2Img Generation (Fixed Approach)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Txt2Img Fast Generation (Fixed)")
    print("=" * 70)

    before_count = count_results(page)
    print(f"  Results before: {before_count}")

    # Navigate to Enhance (distant tool at 628), then to Txt2Img (197)
    print("  Navigating: Enhance → Txt2Img...")
    page.mouse.click(40, 628)  # Enhance
    page.wait_for_timeout(2000)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2500)

    # Verify we're on Txt2Img
    panel_text = get_panel_text(page)
    first_line = panel_text.split("\n")[0]
    print(f"  Panel: {first_line}")

    if "Text to Image" not in panel_text and "Txt2Img" not in first_line:
        print("  WARNING: Not on Txt2Img panel! Trying again...")
        page.mouse.click(40, 766)  # Storyboard
        page.wait_for_timeout(1500)
        page.mouse.click(40, 197)  # Txt2Img
        page.wait_for_timeout(2500)
        panel_text = get_panel_text(page)
        first_line = panel_text.split("\n")[0]
        print(f"  Panel (retry): {first_line}")

    # Select Fast mode (2 credits)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        for (var btn of panel.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Fast') { btn.click(); return true; }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Fill prompt using keyboard (more reliable than JS value setting)
    test_prompt = "A pair of premium wireless over-ear headphones with brushed aluminum finish on a clean white studio background. Professional product photography, soft even lighting, sharp focus, commercial grade. No text, no watermarks."

    # Click and focus the textarea, then type
    ta_click = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return { found: false, reason: 'no panel' };
        var ta = panel.querySelector('textarea.len-1800, textarea');
        if (!ta) return { found: false, reason: 'no textarea' };
        ta.focus();
        ta.click();
        return { found: true };
    }""")
    print(f"  Textarea focus: {json.dumps(ta_click)}")

    if ta_click.get("found"):
        # Select all and delete first
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.press("Delete")
        page.wait_for_timeout(200)

        # Type prompt
        page.keyboard.type(test_prompt, delay=2)
        page.wait_for_timeout(500)

        # Verify prompt
        current_prompt = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            var ta = panel.querySelector('textarea');
            return ta ? ta.value.substring(0, 100) : '';
        }""")
        print(f"  Prompt filled: '{current_prompt[:80]}...' ({len(current_prompt)} chars)")

    # Check generate button
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
        };
    }""")
    print(f"  Generate button: {json.dumps(gen_state)}")
    screenshot(page, "p174_txt2img_ready")

    if gen_state.get("ready"):
        print("\n  >>> GENERATING (Fast mode, 2 credits) <<<")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var btn = panel.querySelector('.generative.ready, #txt2img-generate-btn');
            if (btn && !btn.disabled) btn.click();
        }""")

        # Poll for completion
        start_time = time.time()
        last_progress = ""
        while time.time() - start_time < 90:
            page.wait_for_timeout(3000)

            # Check for progress
            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var txt = (el.innerText || '').trim();
                    if (/^\\d{1,3}%$/.test(txt)) {
                        var r = el.getBoundingClientRect();
                        if (r.x > 1000) return txt;  // Progress in right panel
                    }
                }
                return '';
            }""")
            if progress and progress != last_progress:
                print(f"    Progress: {progress} ({int(time.time() - start_time)}s)")
                last_progress = progress

            current_count = count_results(page)
            if current_count > before_count:
                elapsed = int(time.time() - start_time)
                print(f"\n  GENERATION COMPLETE! {elapsed}s, new images: {current_count - before_count}")
                break
        else:
            final_count = count_results(page)
            if final_count > before_count:
                print(f"\n  GENERATION COMPLETE (detected late)! New images: {final_count - before_count}")
            else:
                print(f"\n  TIMEOUT. Results count unchanged: {final_count}")

        screenshot(page, "p174_txt2img_result")

        # Extract newest result URL
        newest_urls = page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            var urls = [];
            for (var img of imgs) urls.push(img.src);
            return urls.slice(-4);  // last 4
        }""")
        print(f"  Latest result URLs:")
        for url in newest_urls:
            print(f"    {url[:150]}")
    else:
        print("  Generate button NOT ready — need to investigate")

    # ================================================================
    # TASK 2: Layer Interaction — Select and Unlock
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Layer Interaction")
    print("=" * 70)

    # Switch to Layers tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.header-item')) {
            if ((el.innerText || '').includes('Layer')) { el.click(); return true; }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Map layer items more thoroughly
    layers = page.evaluate("""() => {
        var items = document.querySelectorAll('.layer-item');
        var results = [];
        for (var item of items) {
            var rect = item.getBoundingClientRect();
            if (rect.height === 0) continue;
            var className = (typeof item.className === 'string') ? item.className : (item.getAttribute('class') || '');

            // Find sub-elements (lock icon, visibility eye, thumbnail)
            var children = [];
            for (var child of item.querySelectorAll('*')) {
                var cr = child.getBoundingClientRect();
                if (cr.height > 0 && cr.height < 30) {
                    var cc = (typeof child.className === 'string') ? child.className : (child.getAttribute('class') || '');
                    if (cc.includes('lock') || cc.includes('eye') || cc.includes('vis') || cc.includes('thumb') || cc.includes('icon')) {
                        children.push({
                            class: cc.substring(0, 50),
                            tag: child.tagName,
                            pos: { x: Math.round(cr.x), y: Math.round(cr.y) }
                        });
                    }
                }
            }

            results.push({
                text: (item.innerText || '').trim().substring(0, 60),
                class: className.substring(0, 80),
                locked: className.includes('locked'),
                selected: className.includes('selected') || className.includes('active'),
                pos: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
                children: children
            });
        }
        return results;
    }""")
    print(f"  Layers ({len(layers)}):")
    for layer in layers:
        flags = []
        if layer['locked']: flags.append("LOCKED")
        if layer['selected']: flags.append("SELECTED")
        print(f"    '{layer['text'][:30]}' {' '.join(flags)} at ({layer['pos']['x']},{layer['pos']['y']}) {layer['pos']['w']}x{layer['pos']['h']}")
        for child in layer['children'][:5]:
            print(f"      {child['tag']}.{child['class'][:30]} at ({child['pos']['x']},{child['pos']['y']})")

    # Try clicking a layer to select it
    if layers:
        first_layer = layers[0]
        print(f"\n  Clicking first layer: '{first_layer['text'][:30]}'")
        page.mouse.click(first_layer['pos']['x'] + 50, first_layer['pos']['y'] + 32)
        page.wait_for_timeout(1000)

        # Check action bar state after selection
        action_bar_state = page.evaluate("""() => {
            var toolbar = document.querySelector('.layer-tools');
            if (!toolbar) return { found: false };
            var className = (typeof toolbar.className === 'string') ? toolbar.className : (toolbar.getAttribute('class') || '');
            return {
                found: true,
                disabled: className.includes('disabled'),
                text: toolbar.innerText.substring(0, 200)
            };
        }""")
        print(f"  Action bar after selection: {json.dumps(action_bar_state)}")
        screenshot(page, "p174_layer_selected")

    # ================================================================
    # TASK 3: Explore Canvas Zoom and Navigation
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Canvas Zoom Controls")
    print("=" * 70)

    zoom = page.evaluate("""() => {
        // Find zoom display
        for (var el of document.querySelectorAll('*')) {
            var txt = (el.innerText || '').trim();
            if (/^\\d{1,3}%$/.test(txt)) {
                var rect = el.getBoundingClientRect();
                if (rect.y < 50 && rect.x > 900) {
                    return {
                        text: txt,
                        pos: { x: Math.round(rect.x), y: Math.round(rect.y) },
                        tag: el.tagName,
                        class: (typeof el.className === 'string') ? el.className.substring(0, 40) : ''
                    };
                }
            }
        }
        return { found: false };
    }""")
    print(f"  Zoom level: {json.dumps(zoom)}")

    # ================================================================
    # TASK 4: Map generation credit consumption in real-time
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Credit Balance Check")
    print("=" * 70)

    credits = page.evaluate("""() => {
        var credits = document.querySelector('.c-credit, .credit-content');
        if (!credits) return { found: false };
        return {
            found: true,
            text: (credits.innerText || '').trim(),
            imageCredits: 'Unlimited',
            videoCredits: ''
        };
    }""")
    if credits.get("found"):
        parts = credits['text'].split('\n')
        print(f"  Credit display: {' / '.join(p.strip() for p in parts if p.strip())}")
    else:
        print(f"  Credits: {json.dumps(credits)}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 9 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
