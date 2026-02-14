"""Phase 17: Select Ray character, generate CC image, test Chat Editor, explore tools.

Fixes from Phase 16:
- Results are in CENTER panel (x ~350-700), not right panel
- Ray needs to be CLICKED in the character dropdown
- Chat editor: click "Describe the desired image" placeholder at bottom
- CC textarea placeholder: "Descreva o que você quer criar com o personagem"
"""

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from tools.lib.brave_profile import connect_or_launch

OUT_DIR = _ROOT / "artifacts" / "dzine-explore"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_N = 0


def ss(page, name):
    global _N
    _N += 1
    path = OUT_DIR / f"K{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: K{_N:02d}_{name}")


def close_all_dialogs(page):
    for _ in range(8):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click()
                    page.wait_for_timeout(500)
                    found = True
            except Exception:
                pass
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
        if not found:
            break


def count_center_results(page):
    """Count result sections in the center panel (x 350-700)."""
    return page.evaluate("""() => {
        let c = 0;
        // Count result header labels (Text-to-Image, Character Sheet, Consistent Character, etc.)
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const rect = el.getBoundingClientRect();
            if (rect.x > 340 && rect.x < 700 && rect.y > 60 && rect.width > 100 &&
                (text === 'Text-to-Image' || text === 'Character Sheet' ||
                 text === 'Consistent Character' || text === 'Chat Editor') &&
                el.children.length < 3) {
                c++;
            }
        }
        return c;
    }""")


def count_result_images(page):
    """Count actual result images in the center panel."""
    return page.evaluate("""() => {
        let c = 0;
        for (const img of document.querySelectorAll('img')) {
            const r = img.getBoundingClientRect();
            // Center panel result images: x between 340-1050, y > 60, decent size
            if (r.x > 340 && r.x < 1050 && r.y > 80 && r.width > 80 && r.height > 80) c++;
        }
        return c;
    }""")


def wait_for_generation(page, timeout_s=120, label=""):
    """Wait for generation to complete by watching the center panel."""
    start = time.monotonic()

    # Watch for "Starting a task..." → "Generation Complete!" transition
    while time.monotonic() - start < timeout_s:
        page.wait_for_timeout(5000)
        elapsed = time.monotonic() - start

        status = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.width > 50 && rect.y > 50 && rect.y < 200) {
                    if (text === 'Starting a task...' || text.includes('Generating')) {
                        return 'generating';
                    }
                    if (text === 'Generation Complete!' || text === 'Submitted!') {
                        return 'submitted';
                    }
                }
            }
            // Check if Generate button is back (not disabled, not "Submitted!")
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text.startsWith('Generate') && rect.x > 60 && rect.x < 500 &&
                    rect.y > 500 && !btn.disabled) {
                    return 'ready';
                }
            }
            return 'unknown';
        }""")

        # Also count images in center
        imgs = count_result_images(page)
        print(f"  ... {elapsed:.0f}s status={status} imgs={imgs}")

        if status == 'ready' and elapsed > 10:
            # Generation finished, button is ready again
            print(f"  Generation complete in {elapsed:.0f}s!")
            ss(page, f"gen_done_{label}")
            return True

    print(f"  Timed out after {timeout_s}s")
    ss(page, f"gen_timeout_{label}")
    return False


def map_panel(page, label=""):
    items = page.evaluate("""() => {
        const items = [];
        const seen = new Set();
        for (const el of document.querySelectorAll('*')) {
            const rect = el.getBoundingClientRect();
            if (rect.x > 60 && rect.x < 500 && rect.y > 50 && rect.y < 900 &&
                rect.width > 15 && rect.height > 5) {
                const text = (el.innerText || '').trim();
                if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                    seen.add(text);
                    items.push({text: text.substring(0, 80), tag: el.tagName,
                                x: Math.round(rect.x), y: Math.round(rect.y),
                                w: Math.round(rect.width), h: Math.round(rect.height)});
                }
            }
        }
        return items.sort((a, b) => a.y - b.y).slice(0, 50);
    }""")
    print(f"\n  {label} ({len(items)} items):")
    for item in items:
        print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> {item['text']}")
    return items


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    # Find the canvas page
    page = None
    for p in context.pages:
        if "canvas?id=19797967" in p.url:
            page = p
            break

    if not page:
        page = context.new_page()
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("https://www.dzine.ai/canvas?id=19797967",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(8000)
        close_all_dialogs(page)
        page.wait_for_timeout(2000)

    page.set_viewport_size({"width": 1440, "height": 900})
    page.bring_to_front()
    page.wait_for_timeout(1000)
    close_all_dialogs(page)
    ss(page, "start")

    try:
        # ================================================================
        # STEP 1: CONSISTENT CHARACTER — Select Ray + Generate (4 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 1: CC — Select Ray + Generate (4 credits)")
        print("=" * 60)

        # Click Character sidebar icon
        page.mouse.click(40, 306)
        page.wait_for_timeout(1500)
        close_all_dialogs(page)

        # Click "Generate Images" button
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('button, div')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Generate Images' && rect.x > 60 && rect.x < 350 &&
                    rect.y > 200 && rect.y < 300 && rect.width > 100) {
                    el.click();
                    return true;
                }
            }
            // Try the parent button
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                if (text.includes('Generate Images') && text.includes('With your character')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        close_all_dialogs(page)
        ss(page, "cc_panel_open")

        # Now click "Choose a Character" dropdown to open the character list
        print("\n  Opening character dropdown...")
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('button, div')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Choose a Character' && rect.x > 60 && rect.x < 300 && rect.width > 100) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1500)
        ss(page, "char_dropdown")

        # Click "Ray" in the character list
        print("  Selecting Ray...")
        ray_clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                // Ray should be in the dropdown area, last item
                if (text === 'Ray' && rect.width > 10 && rect.height > 10 &&
                    rect.x > 150 && rect.x < 500 && rect.y > 100) {
                    // Click the parent container (the whole row)
                    const parent = el.closest('[class*="character"]') || el.closest('[class*="item"]') || el.parentElement;
                    (parent || el).click();
                    return {x: rect.x, y: rect.y, clicked: 'parent'};
                }
            }
            // Fallback: click any element with just "Ray" text
            for (const el of document.querySelectorAll('div, span, p')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Ray' && rect.x > 150 && rect.y > 100) {
                    el.click();
                    return {x: rect.x, y: rect.y, clicked: 'direct'};
                }
            }
            return null;
        }""")
        print(f"  Ray click: {ray_clicked}")
        page.wait_for_timeout(2000)
        close_all_dialogs(page)
        ss(page, "ray_selected")

        # Verify Ray is selected
        ray_info = page.evaluate("""() => {
            // Look for Ray's name/description in the CC panel
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.includes('Ray') && rect.x > 60 && rect.x < 350 && rect.y > 50 && rect.y < 120) {
                    return {text: text.substring(0, 60), x: rect.x, y: rect.y};
                }
            }
            // Check if "Choose a Character" is still showing
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Choose a Character' && el.getBoundingClientRect().x > 60) {
                    return {text: 'NOT SELECTED', x: 0, y: 0};
                }
            }
            return null;
        }""")
        print(f"  Ray selection status: {ray_info}")

        # Now fill the scene textarea
        print("\n  Finding scene textarea...")
        textarea = page.evaluate("""() => {
            for (const el of document.querySelectorAll('textarea')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 350 && rect.width > 100 && rect.height > 20) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                            placeholder: el.placeholder || ''};
                }
            }
            return null;
        }""")
        print(f"  Textarea: {textarea}")

        if textarea:
            page.mouse.click(textarea["x"] + 50, textarea["y"] + 15)
            page.wait_for_timeout(300)
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(100)

            scene = "Standing behind a modern desk in a minimalist studio, one hand resting on desk, confident smile, looking directly at camera, soft studio lighting, clean white background"
            page.keyboard.type(scene, delay=5)
            page.wait_for_timeout(500)
            ss(page, "cc_scene_typed")
            print(f"  Typed scene ({len(scene)} chars)")
        else:
            print("  Textarea not found — checking if panel needs scroll")
            # The textarea might be collapsed or hidden. Map the full panel.
            map_panel(page, "CC Panel State")

        # Click Generate
        print("\n  Looking for Generate button...")
        gen_btn = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text.includes('Generate') && rect.x > 60 && rect.x < 350 &&
                    rect.y > 400 && !btn.disabled && rect.width > 100) {
                    return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                            w: rect.width, h: rect.height, disabled: btn.disabled};
                }
            }
            return null;
        }""")
        print(f"  Generate: {gen_btn}")

        if gen_btn and 'Generate' in gen_btn.get('text', ''):
            # Check warning message
            warning = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text.includes('Please') && rect.x > 60 && rect.x < 350 && rect.y > 450) {
                        return text;
                    }
                }
                return null;
            }""")
            if warning:
                print(f"  Warning: {warning}")

            print("  CLICKING GENERATE!")
            page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
            page.wait_for_timeout(1000)
            ss(page, "cc_generating")

            page.wait_for_timeout(2000)
            close_all_dialogs(page)

            success = wait_for_generation(page, timeout_s=90, label="cc")
            if success:
                ss(page, "cc_result")
                print("  CC Generation succeeded!")

        # Close CC panel
        page.evaluate("""() => {
            // Click the X button to close the CC panel
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if ((text === '×' || text === 'x' || text === '✕') && rect.x > 140 && rect.x < 200 && rect.y < 80) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # ================================================================
        # STEP 2: CHAT EDITOR (20 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 2: CHAT EDITOR (20 credits)")
        print("=" * 60)

        # Close any panel first
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # The chat bar is at the bottom center — find "Describe the desired image"
        print("\n  Looking for chat editor bar...")
        chat_bar = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.includes('Describe the desired image') && rect.y > 700 && rect.width > 100) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                }
            }
            return null;
        }""")
        print(f"  Chat bar placeholder: {chat_bar}")

        if chat_bar:
            # Click on the placeholder to activate the chat editor
            page.mouse.click(chat_bar["x"] + chat_bar["w"]//2, chat_bar["y"] + chat_bar["h"]//2)
            page.wait_for_timeout(1500)
            close_all_dialogs(page)
            ss(page, "chat_activated")

            # Now look for the expanded chat input
            chat_input = page.evaluate("""() => {
                for (const el of document.querySelectorAll('[contenteditable=\"true\"]')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 100 && rect.height > 10 && rect.y > 500) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'contenteditable'};
                    }
                }
                for (const el of document.querySelectorAll('textarea')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 100 && rect.y > 500) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'textarea'};
                    }
                }
                return null;
            }""")
            print(f"  Chat input: {chat_input}")

            if chat_input:
                # Check if it's visible within viewport
                if chat_input["y"] > 900:
                    print(f"  Chat input at y={chat_input['y']} — below viewport, scrolling...")
                    # Try scrolling the page or expanding the chat area
                    page.evaluate("window.scrollBy(0, 200)")
                    page.wait_for_timeout(500)

                page.mouse.click(chat_input["x"] + 50, min(chat_input["y"], 880) + 10)
                page.wait_for_timeout(300)

                prompt = "Ray, young adult male YouTuber with light skin and short dark hair, charcoal gray t-shirt. Standing in a clean modern studio holding a product box in his right hand, showing it to camera with enthusiastic smile. Minimalist white background, soft professional lighting. Medium shot waist up. Photorealistic, 4K."
                page.keyboard.type(prompt, delay=3)
                page.wait_for_timeout(500)
                ss(page, "chat_typed")
                print(f"  Typed prompt ({len(prompt)} chars)")

                # Find Generate button in chat area
                gen_btn = page.evaluate("""() => {
                    for (const btn of document.querySelectorAll('button')) {
                        const text = (btn.innerText || '').trim();
                        const rect = btn.getBoundingClientRect();
                        if (text.includes('Generate') && rect.y > 500 && !btn.disabled) {
                            return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                                    w: rect.width, h: rect.height};
                        }
                    }
                    // Also try the yellow circular button next to the chat input
                    for (const btn of document.querySelectorAll('button')) {
                        const rect = btn.getBoundingClientRect();
                        if (rect.y > 700 && rect.x > 400 && rect.width < 60 && rect.width > 20 &&
                            rect.height < 60 && rect.height > 20 && !btn.disabled) {
                            const hasSvg = !!btn.querySelector('svg');
                            if (hasSvg) {
                                return {text: 'send_icon', x: rect.x, y: rect.y,
                                        w: rect.width, h: rect.height};
                            }
                        }
                    }
                    return null;
                }""")
                print(f"  Generate button: {gen_btn}")

                if gen_btn:
                    print("  CLICKING GENERATE!")
                    page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
                    page.wait_for_timeout(1000)
                    ss(page, "chat_generating")

                    page.wait_for_timeout(2000)
                    close_all_dialogs(page)

                    success = wait_for_generation(page, timeout_s=120, label="chat")
                    if success:
                        print("  Chat Editor generation succeeded!")
                        ss(page, "chat_result")
                else:
                    print("  No Generate button found for chat")
                    # Map all buttons near bottom
                    btns = page.evaluate("""() => {
                        const btns = [];
                        for (const btn of document.querySelectorAll('button, [role="button"]')) {
                            const rect = btn.getBoundingClientRect();
                            if (rect.y > 700 && rect.width > 10 && rect.height > 10) {
                                btns.push({text: (btn.innerText || '').trim().substring(0, 20),
                                          x: Math.round(rect.x), y: Math.round(rect.y),
                                          w: Math.round(rect.width), h: Math.round(rect.height),
                                          disabled: btn.disabled});
                            }
                        }
                        return btns.slice(0, 10);
                    }""")
                    print("  Bottom buttons:")
                    for b in btns:
                        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} '{b['text']}' disabled={b['disabled']}")
            else:
                print("  Chat input not found after activation")
                ss(page, "chat_no_input")
        else:
            print("  Chat bar placeholder not found")

        # ================================================================
        # STEP 3: EXPLORE RESULT ACTIONS ON GENERATED IMAGE
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 3: RESULT ACTIONS ON TXT2IMG IMAGE")
        print("=" * 60)

        # Close any open panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Click "Results" tab to switch to results view
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Results' && rect.y < 80 && rect.x > 300 && rect.x < 600) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)
        ss(page, "results_tab")

        # Look for all result sections
        results = page.evaluate("""() => {
            const sections = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.x > 340 && rect.x < 800 && rect.y > 60 && rect.width > 50 &&
                    (text === 'Text-to-Image' || text === 'Character Sheet' ||
                     text === 'Consistent Character' || text === 'Chat Editor') &&
                    el.children.length < 3) {
                    sections.push({type: text, x: Math.round(rect.x), y: Math.round(rect.y)});
                }
            }
            return sections;
        }""")
        print(f"\n  Result sections: {results}")

        # Get the first result image (from Txt2Img)
        first_result = page.evaluate("""() => {
            for (const img of document.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.x > 340 && r.x < 800 && r.y > 100 && r.width > 80 && r.height > 80) {
                    return {src: img.src.substring(0, 120), x: r.x, y: r.y,
                           w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
            return null;
        }""")
        print(f"  First result: {first_result}")

        if first_result:
            # Hover over it to see action buttons
            page.mouse.move(first_result["x"] + first_result["w"]//2,
                           first_result["y"] + first_result["h"]//2)
            page.wait_for_timeout(1000)
            ss(page, "result_hover")

            # Click on it to see what happens
            page.mouse.click(first_result["x"] + first_result["w"]//2,
                            first_result["y"] + first_result["h"]//2)
            page.wait_for_timeout(1500)
            ss(page, "result_clicked")

            # Check what happened — did it place on canvas? Did a preview open?
            layer_count = page.evaluate("""() => {
                let c = 0;
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text.includes('Layer') && rect.x > 1050 && rect.y > 60) c++;
                }
                return c;
            }""")
            print(f"  Layers after click: {layer_count}")

            # Try the "Select" button that appeared on hover in Phase 16
            select_btn = page.evaluate("""() => {
                for (const el of document.querySelectorAll('button, div')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text === 'Select' && rect.x > 340 && rect.y > 60) {
                        el.click();
                        return {x: rect.x, y: rect.y};
                    }
                }
                return null;
            }""")
            print(f"  Select button: {select_btn}")
            if select_btn:
                page.wait_for_timeout(1500)
                ss(page, "result_selected")

        # ================================================================
        # STEP 4: PLACE ON CANVAS + SELECT LAYER
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 4: PLACE ON CANVAS")
        print("=" * 60)

        # Check if image was placed on canvas (look for new layer)
        layers = page.evaluate("""() => {
            const layers = [];
            // Click Layers tab first
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Layers' && rect.x > 1050 && rect.y < 80) {
                    el.click();
                    break;
                }
            }
            // Wait and find layer items
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.startsWith('Layer') && rect.x > 1050 && rect.y > 80 && rect.height < 80) {
                    layers.push({text, x: Math.round(rect.x), y: Math.round(rect.y)});
                }
            }
            return layers;
        }""")
        print(f"\n  Canvas layers: {layers}")
        ss(page, "canvas_layers")

        # Select Layer 1 (click on canvas center where the image is)
        page.mouse.click(600, 400)
        page.wait_for_timeout(1000)

        # Check if a layer is selected — top toolbar should show processing tools
        top_tools = page.evaluate("""() => {
            const tools = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.y > 30 && rect.y < 80 && rect.x > 200 && rect.x < 800 &&
                    text.length > 2 && text.length < 30 && rect.width > 30 &&
                    el.children.length < 3) {
                    tools.push({text, x: Math.round(rect.x)});
                }
            }
            const seen = new Set();
            return tools.filter(t => { if (seen.has(t.text)) return false; seen.add(t.text); return true; });
        }""")
        print(f"\n  Top toolbar when layer selected:")
        for t in top_tools:
            print(f"    x={t['x']} '{t['text']}'")

        # ================================================================
        # STEP 5: TRY EXPRESSION EDIT ON RESULT
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 5: EXPRESSION EDIT")
        print("=" * 60)

        # Click "Expression Edit" action button on the Txt2Img result
        # First, switch to Results tab
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Results' && rect.y < 80 && rect.x > 300) {
                    el.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(500)

        # Find and click "Expression Edit" button below the first result
        expr_clicked = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button, div')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text === 'Expression Edit' && rect.x > 340 && rect.y > 200 &&
                    rect.width > 100 && rect.height > 20) {
                    btn.click();
                    return {x: rect.x, y: rect.y};
                }
            }
            return null;
        }""")
        print(f"\n  Expression Edit click: {expr_clicked}")

        if expr_clicked:
            page.wait_for_timeout(3000)
            close_all_dialogs(page)
            ss(page, "expression_edit")

            # Map what appeared
            expr_panel = page.evaluate("""() => {
                const items = [];
                const seen = new Set();
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 20 && rect.height > 10 && text && text.length > 1 &&
                        text.length < 80 && el.children.length < 4 && !seen.has(text)) {
                        seen.add(text);
                        items.push({text: text.substring(0, 60), x: Math.round(rect.x),
                                   y: Math.round(rect.y), w: Math.round(rect.width)});
                    }
                }
                return items.filter(i => i.y > 50 && i.y < 900).sort((a, b) => a.y - b.y).slice(0, 30);
            }""")
            print(f"  Expression Edit panel:")
            for item in expr_panel:
                print(f"    ({item['x']},{item['y']}) w={item['w']} '{item['text']}'")
        else:
            print("  Expression Edit button not found")

        # ================================================================
        # STEP 6: EXPLORE STYLES IN TXT2IMG
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 6: EXPLORE STYLES")
        print("=" * 60)

        # Go back to normal state
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # Click Txt2Img
        page.mouse.click(40, 197)
        page.wait_for_timeout(1500)
        close_all_dialogs(page)

        # Click on the style selector (Nano Banana Pro button with >)
        style_btn = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.includes('Nano Banana Pro') && rect.x > 60 && rect.x < 350 &&
                    rect.y > 80 && rect.y < 150) {
                    el.click();
                    return {x: rect.x, y: rect.y, text};
                }
            }
            return null;
        }""")
        print(f"\n  Style selector: {style_btn}")

        if style_btn:
            page.wait_for_timeout(2000)
            ss(page, "style_picker")

            # Map available styles
            styles = page.evaluate("""() => {
                const styles = [];
                const seen = new Set();
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    // Styles usually appear in a grid or list
                    if (rect.width > 20 && rect.height > 20 && text && text.length > 2 &&
                        text.length < 40 && el.children.length < 3 && !seen.has(text)) {
                        // Filter for likely style names (not generic UI)
                        if (rect.x > 60 && rect.x < 700 && rect.y > 80 && rect.y < 800) {
                            seen.add(text);
                            styles.push({name: text, x: Math.round(rect.x), y: Math.round(rect.y)});
                        }
                    }
                }
                return styles.sort((a, b) => a.y - b.y).slice(0, 40);
            }""")
            print(f"\n  Available styles ({len(styles)}):")
            for s in styles:
                print(f"    ({s['x']},{s['y']}) {s['name']}")

        # ================================================================
        # FINAL: CREDIT CHECK + SUMMARY
        # ================================================================
        print("\n" + "=" * 60)
        print("  FINAL: CREDITS + SUMMARY")
        print("=" * 60)

        credits = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.y < 35 && rect.x > 900 && text && text.length < 30) {
                    items.push({text, x: Math.round(rect.x)});
                }
            }
            const seen = new Set();
            return items.filter(r => { if (seen.has(r.text)) return false; seen.add(r.text); return true; })
                       .sort((a, b) => a.x - b.x);
        }""")
        print(f"\n  Credits:")
        for c in credits:
            print(f"    x={c['x']} '{c['text']}'")

        ss(page, "final")
        print("\n\n===== PHASE 17 COMPLETE =====")

    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        ss(page, "error")
    finally:
        if should_close:
            context.close()
        pw.stop()


if __name__ == "__main__":
    main()
