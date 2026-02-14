#!/usr/bin/env python3
"""Dzine Deep Exploration Part 20 — Safe Panel Switching + Img2Img + Chat Editor.

SAFETY: Always verify panel type before clicking Generate.

1. Close all open panels/dialogs first
2. Navigate to Img2Img safely (close AI Video first)
3. Select Nano Banana Pro model for Img2Img
4. Generate at 4K quality (max)
5. Chat Editor model listing
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


def close_everything(page):
    """Close all dialogs, overlays, and panels."""
    # Close Sound Effects / Pick Image / other dialogs
    page.evaluate("""() => {
        // Close any X buttons on popups
        for (var el of document.querySelectorAll('.ico-close, [class*="close-btn"], [class*="close-icon"]')) {
            if (el.offsetHeight > 0) el.click();
        }
        // Close common dialogs
        for (var text of ['Not now', 'Close', 'Never show again', 'Got it', 'Skip', 'Later']) {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === text && btn.offsetHeight > 0) btn.click();
            }
        }
    }""")
    page.wait_for_timeout(500)
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)


def get_active_panel(page):
    """Return which panel/tool is currently active."""
    return page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        var text = (panel.innerText || '').substring(0, 50).trim();
        if (text.startsWith('Text to Image')) return 'txt2img';
        if (text.startsWith('AI Video')) return 'ai_video';
        if (text.startsWith('Enhance & Upscale')) return 'enhance';
        if (text.startsWith('Motion Control')) return 'motion';
        if (text.startsWith('Face Swap')) return 'face_swap';
        if (text.includes('Img2Img') || text.includes('Image to Image')) return 'img2img';
        // Check for Img2Img panel markers
        var hasStructure = !!panel.querySelector('[class*="structure"]');
        if (hasStructure) return 'img2img';
        return 'unknown:' + text.substring(0, 30);
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 20")
    print("Safe Panel Switching + Img2Img + Chat Editor")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")
    print(f"  Tabs: {len(context.pages)}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # Step 0: Close everything
    close_everything(page)
    print(f"  Active panel after cleanup: {get_active_panel(page)}")

    # ================================================================
    # TASK 1: Navigate to Txt2Img safely
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Navigate to Txt2Img (close other panels first)")
    print("=" * 70)

    # Close the current left panel by clicking its X
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
    }""")
    page.wait_for_timeout(500)

    # Click Txt2Img sidebar icon
    page.mouse.click(40, 190)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  After Txt2Img click: {panel}")

    if panel != 'txt2img':
        # Try the exact sidebar approach
        print("  Trying alternative sidebar navigation...")
        # Click away first to deselect
        page.mouse.click(700, 400)
        page.wait_for_timeout(500)
        # Then click Txt2Img
        page.mouse.click(40, 190)
        page.wait_for_timeout(2500)
        panel = get_active_panel(page)
        print(f"  After retry: {panel}")

    # Verify model
    model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Current model: {model}")

    if model != 'Nano Banana Pro':
        print("  Selecting Nano Banana Pro...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var btn = panel.querySelector('button.style');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(2000)
        nbp_pos = page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return null;
            for (var el of picker.querySelectorAll('span, div')) {
                if ((el.innerText || '').trim() === 'Nano Banana Pro') {
                    var r = el.getBoundingClientRect();
                    if (r.height < 30 && r.height > 0) return {x: r.x + r.width/2, y: r.y - 60};
                }
            }
            return null;
        }""")
        if nbp_pos:
            page.mouse.click(nbp_pos['x'], nbp_pos['y'])
            page.wait_for_timeout(1000)
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

    # Select 4K quality (maximum)
    print("  Selecting 4K quality...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        for (var btn of panel.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === '4K') { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    # Select 16:9 aspect ratio
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        for (var el of panel.querySelectorAll('[class*="aspect"] *, [class*="ratio"] *')) {
            if ((el.innerText || '').trim() === '16:9') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    # Check settings
    settings = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {};
        var text = panel.innerText || '';
        var match = text.match(/(\\d+)[x\u00d7](\\d+)/);
        var quality = '';
        for (var btn of panel.querySelectorAll('button.options.selected, button[class*="selected"]')) {
            var t = (btn.innerText || '').trim();
            if (['1K', '2K', '4K'].includes(t)) quality = t;
        }
        return {
            dims: match ? match[0] : 'unknown',
            quality: quality
        };
    }""")
    print(f"  Settings: {json.dumps(settings)}")

    # Generate a product image prompt with high-fidelity focus
    prompt = "Professional product photography of premium wireless headphones with gold metallic finish, isolated on pure white background, studio lighting with soft diffusion, extremely detailed, 8K quality, commercial product shot, clean shadows, photorealistic"
    page.evaluate("""(p) => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var ta = panel.querySelector('textarea');
        if (ta) {
            ta.focus();
            ta.value = p;
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""", prompt)
    page.wait_for_timeout(300)

    screenshot(page, "p191_txt2img_4k_setup")

    # SAFETY: Verify we're in Txt2Img before generating
    panel_check = get_active_panel(page)
    print(f"  Panel before generate: {panel_check}")

    if panel_check == 'txt2img' or panel_check.startswith('unknown:Text'):
        # Verify credit cost shows 40 (4K NBP)
        cost = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'no panel';
            var gen = panel.querySelector('.generative, #txt2img-generate-btn');
            return gen ? (gen.innerText || '').trim() : 'no gen btn';
        }""")
        print(f"  Generate button text: {cost}")

        # Generate
        gen = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var btn = panel.querySelector('.generative, #txt2img-generate-btn');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }""")
        print(f"  Generate clicked: {gen}")

        if gen:
            print("  Waiting for 4K NBP generation (90s max)...")
            page.wait_for_timeout(70000)
            screenshot(page, "p191_4k_result")
            print("  Generation complete!")
    else:
        print(f"  SKIPPING Generate — wrong panel: {panel_check}")

    # ================================================================
    # TASK 2: Img2Img navigation
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Navigate to Img2Img")
    print("=" * 70)

    # Close Txt2Img panel
    close_everything(page)
    page.wait_for_timeout(500)

    # Click Img2Img sidebar
    page.mouse.click(40, 240)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  After Img2Img click: {panel}")

    # Map the panel
    img2img_info = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {text: 'NO PANEL'};
        return {
            panelText: (panel.innerText || '').substring(0, 400),
            hasStructure: !!panel.querySelector('[class*="structure"]'),
            hasColorMatch: !!panel.querySelector('[class*="color"]')
        };
    }""")

    print(f"  Has Structure Match: {img2img_info.get('hasStructure', False)}")
    print(f"  Has Color Match: {img2img_info.get('hasColorMatch', False)}")
    print(f"  Panel text:")
    for line in img2img_info.get('panelText', '').split('\n')[:15]:
        line = line.strip()
        if line:
            print(f"    > {line[:50]}")

    screenshot(page, "p191_img2img_panel")

    # ================================================================
    # TASK 3: Chat Editor Models
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Chat Editor Model List")
    print("=" * 70)

    # Close panels
    close_everything(page)
    page.wait_for_timeout(500)

    # Click model selector in bottom bar
    model_btn_pos = page.evaluate("""() => {
        var btn = document.querySelector('.option-btn');
        if (btn && btn.offsetHeight > 0) {
            var rect = btn.getBoundingClientRect();
            return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
        }
        return null;
    }""")

    if model_btn_pos:
        print(f"  Model button at ({model_btn_pos['x']}, {model_btn_pos['y']})")
        page.mouse.click(model_btn_pos['x'], model_btn_pos['y'])
        page.wait_for_timeout(1000)

        # Get model names using textContent and data attributes
        models = page.evaluate("""() => {
            var list = document.querySelector('.option-list');
            if (!list) return [];
            var items = [];
            for (var item of list.querySelectorAll('.option-item')) {
                // Try multiple ways to get the name
                var nameEl = item.querySelector('.name, .model-name, span, div');
                var name = '';
                if (nameEl) {
                    name = (nameEl.textContent || nameEl.innerText || '').trim();
                }
                if (!name) {
                    name = (item.textContent || item.innerText || '').trim();
                }
                var cls = (typeof item.className === 'string') ? item.className : '';
                var rect = item.getBoundingClientRect();
                items.push({
                    name: name.split('\\n')[0].trim(),
                    selected: cls.includes('selected') || cls.includes('active'),
                    y: Math.round(rect.y)
                });
            }
            return items;
        }""")

        if models:
            print(f"\n  Chat Editor models ({len(models)}):")
            for m in models:
                sel = " [SELECTED]" if m.get('selected') else ""
                print(f"    {m['name']}{sel}")
        else:
            # Try alternative: map all visible elements in the option list
            alt_models = page.evaluate("""() => {
                var list = document.querySelector('.option-list');
                if (!list) return {html: 'NO LIST'};
                return {
                    html: list.innerHTML.substring(0, 500),
                    text: (list.innerText || '').substring(0, 300)
                };
            }""")
            print(f"  Alt models text: {alt_models.get('text', '')[:200]}")

        screenshot(page, "p191_chat_models")

        # Close
        page.keyboard.press('Escape')
    else:
        print("  Model button not found")

    # ================================================================
    # TASK 4: Check current credits
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Credit Status")
    print("=" * 70)

    credits = page.evaluate("""() => {
        var text = document.body.innerText || '';
        var match = text.match(/([\\d,.]+)\\s*video\\s*credits/i);
        var videoCredits = match ? match[1] : 'unknown';

        // Also check header credits display
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) {
                return {display: t, videoCredits: videoCredits};
            }
        }
        return {videoCredits: videoCredits};
    }""")
    print(f"  Credits: {json.dumps(credits)}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 20 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
