#!/usr/bin/env python3
"""Dzine Deep Exploration Part 19 — Img2Img + Chat Editor + Tab Cleanup.

1. Clean up excess browser tabs
2. Test Img2Img using canvas image (place result on canvas, then Img2Img)
3. Test Chat Editor with different models
4. Deselect all camera movements, select only Static Shot
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


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 19")
    print("Img2Img + Chat Editor + Tab Cleanup")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()

    # ================================================================
    # TASK 0: Clean up browser tabs
    # ================================================================
    print(f"\n  Browser tabs: {len(context.pages)}")
    pages = context.pages
    canvas_page = None
    for p in pages:
        if "dzine.ai/canvas" in p.url:
            canvas_page = p
            break

    if len(pages) > 3:
        print("  Cleaning up tabs...")
        for p in pages:
            if p != canvas_page and "dzine.ai" not in p.url:
                try:
                    p.close()
                    print(f"    Closed: {p.url[:60]}")
                except:
                    pass
        # Also close duplicate dzine tabs
        dzine_count = 0
        for p in context.pages:
            if "dzine.ai" in p.url:
                dzine_count += 1
                if dzine_count > 1 and p != canvas_page:
                    try:
                        p.close()
                        print(f"    Closed duplicate: {p.url[:60]}")
                    except:
                        pass
        print(f"  Tabs remaining: {len(context.pages)}")

    page = canvas_page or context.pages[0]

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: Camera — Deselect All, Select Only Static Shot
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Camera — Clean Selection (Static Shot Only)")
    print("=" * 70)

    # Open AI Video via results
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)
    page.evaluate("""() => {
        var c = document.querySelectorAll('[class*="result"]');
        for (var el of c) { if (el.scrollHeight > el.clientHeight + 50) el.scrollTop = 0; }
    }""")
    page.wait_for_timeout(500)

    page.evaluate("""() => {
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            if (parent && (parent.innerText || '').trim().startsWith('AI Video')) {
                var btns = c.querySelectorAll('.btn');
                if (btns.length > 0) { btns[0].click(); return true; }
            }
        }
        return false;
    }""")
    page.wait_for_timeout(3000)

    # Expand camera
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var camBtn = panel.querySelector('.camera-movement-btn');
        if (camBtn) camBtn.click();
    }""")
    page.wait_for_timeout(1500)

    # Click Free Selection
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Free Selection') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Deselect all currently selected movements
    selected = page.evaluate("""() => {
        var items = document.querySelectorAll('.selection-item');
        var selected = [];
        for (var item of items) {
            var opt = item.querySelector('.option.selected-option');
            if (opt) {
                var name = (item.innerText || '').trim().split('\\n')[0];
                var opts = item.querySelector('.selection-options');
                if (opts) {
                    var rect = opts.getBoundingClientRect();
                    selected.push({
                        name: name,
                        x: Math.round(rect.x + rect.width/2),
                        y: Math.round(rect.y + rect.height/2)
                    });
                }
            }
        }
        return selected;
    }""")

    print(f"  Currently selected ({len(selected)}):")
    for s in selected:
        print(f"    {s['name']} at ({s['x']}, {s['y']})")

    # Click each selected to deselect
    for s in selected:
        if s['name'] != 'Static Shot':
            print(f"  Deselecting {s['name']}...")
            page.mouse.click(s['x'], s['y'])
            page.wait_for_timeout(500)

    # Now select Static Shot if not already
    static_selected = page.evaluate("""() => {
        var items = document.querySelectorAll('.selection-item');
        for (var item of items) {
            if ((item.innerText || '').includes('Static Shot')) {
                return !!item.querySelector('.option.selected-option');
            }
        }
        return false;
    }""")

    if not static_selected:
        print("  Selecting Static Shot...")
        pos = page.evaluate("""() => {
            var items = document.querySelectorAll('.selection-item');
            for (var item of items) {
                if ((item.innerText || '').includes('Static Shot')) {
                    var opts = item.querySelector('.selection-options');
                    if (opts) {
                        var rect = opts.getBoundingClientRect();
                        return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                    }
                }
            }
            return null;
        }""")
        if pos:
            page.mouse.click(pos['x'], pos['y'])
            page.wait_for_timeout(800)

    # Verify final state
    final = page.evaluate("""() => {
        var items = document.querySelectorAll('.selection-item');
        var result = [];
        for (var item of items) {
            var name = (item.innerText || '').trim().split('\\n')[0];
            var sel = !!item.querySelector('.option.selected-option');
            if (sel) result.push(name);
        }
        return result;
    }""")
    print(f"  Final selected: {final}")
    screenshot(page, "p190_camera_static_only")

    # ================================================================
    # TASK 2: Img2Img — Use canvas content
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Img2Img Workflow")
    print("=" * 70)

    # Close camera overlay
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)

    # First, place a result image on canvas (click result image to select it)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)
    page.evaluate("""() => {
        var c = document.querySelectorAll('[class*="result"]');
        for (var el of c) { if (el.scrollHeight > el.clientHeight + 50) el.scrollTop = 0; }
    }""")
    page.wait_for_timeout(500)

    # Click on the first result image to place on canvas
    placed = page.evaluate("""() => {
        var imgs = document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']");
        if (imgs.length > 0) {
            imgs[0].click();
            return {src: imgs[0].src.substring(0, 80), count: imgs.length};
        }
        return {count: 0};
    }""")
    print(f"  Placed image on canvas: {json.dumps(placed)}")
    page.wait_for_timeout(2000)

    # Switch to Img2Img
    page.mouse.click(40, 240)  # Img2Img sidebar
    page.wait_for_timeout(2500)

    # Map Img2Img panel
    img2img_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {text: 'NO PANEL'};
        var sn = panel.querySelector('.style-name');
        var ta = panel.querySelector('textarea');
        return {
            model: sn ? (sn.innerText || '').trim() : 'unknown',
            hasPrompt: !!ta,
            panelText: (panel.innerText || '').substring(0, 300)
        };
    }""")
    print(f"  Img2Img model: {img2img_panel.get('model', '')}")
    print(f"  Panel text:")
    for line in img2img_panel.get('panelText', '').split('\n')[:12]:
        line = line.strip()
        if line:
            print(f"    > {line[:50]}")

    # Fill a prompt for Img2Img
    prompt = "Premium wireless headphones product photography, studio lighting, clean white background, sharp details, commercial quality"
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

    # Use Describe Canvas feature to auto-generate prompt from canvas
    describe_clicked = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var btn = panel.querySelector('.autoprompt, button.autoprompt');
        if (btn && btn.offsetHeight > 0) { btn.click(); return true; }
        return false;
    }""")
    print(f"  Describe Canvas clicked: {describe_clicked}")
    if describe_clicked:
        page.wait_for_timeout(5000)  # Wait for auto-prompt generation

    screenshot(page, "p190_img2img_panel")

    # Generate Img2Img
    gen_clicked = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        for (var btn of panel.querySelectorAll('button')) {
            if ((btn.innerText || '').includes('Generate') && !btn.disabled) {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Generate clicked: {gen_clicked}")

    if gen_clicked:
        print("  Waiting for Img2Img generation (60s)...")
        page.wait_for_timeout(45000)
        screenshot(page, "p190_img2img_result")
        print("  Generation complete.")

    # ================================================================
    # TASK 3: Chat Editor — Model Selection
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Chat Editor Models")
    print("=" * 70)

    # Click on Chat Editor prompt at bottom
    chat_prompt = page.evaluate("""() => {
        var ce = document.querySelector('#chat-editor-generate-btn');
        if (ce) {
            var rect = ce.getBoundingClientRect();
            return {x: Math.round(rect.x), y: Math.round(rect.y), visible: rect.height > 0};
        }
        // Alternative: find by placeholder
        var ta = document.querySelector('[data-prompt="true"]');
        if (ta) {
            var rect = ta.getBoundingClientRect();
            return {x: Math.round(rect.x), y: Math.round(rect.y), visible: rect.height > 0};
        }
        return null;
    }""")
    print(f"  Chat Editor: {json.dumps(chat_prompt)}")

    # Click model selector button
    model_btn = page.evaluate("""() => {
        var btn = document.querySelector('.option-btn');
        if (btn) {
            var rect = btn.getBoundingClientRect();
            if (rect.height > 0) {
                btn.click();
                return {clicked: true, text: (btn.innerText || '').trim()};
            }
        }
        return {clicked: false};
    }""")
    print(f"  Model button: {json.dumps(model_btn)}")
    page.wait_for_timeout(1000)

    # Map available models
    models = page.evaluate("""() => {
        var list = document.querySelector('.option-list');
        if (!list) return [];
        var items = [];
        for (var item of list.querySelectorAll('.option-item')) {
            var text = (item.innerText || '').trim();
            var cls = (typeof item.className === 'string') ? item.className : '';
            items.push({
                text: text,
                selected: cls.includes('selected') || cls.includes('active')
            });
        }
        return items;
    }""")

    if models:
        print(f"\n  Chat Editor models ({len(models)}):")
        for m in models:
            sel = " [SELECTED]" if m.get('selected') else ""
            print(f"    {m['text']}{sel}")
    else:
        print("  Model list not visible")

    screenshot(page, "p190_chat_models")

    # Close model list
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)

    print("\n" + "=" * 70)
    print("EXPLORATION PART 19 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
