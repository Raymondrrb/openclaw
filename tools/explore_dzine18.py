"""Phase 18: Generate Consistent Character image of Ray.

Key fixes from Phase 17:
- DON'T double-click "Choose a Character" — dropdown opens automatically with CC panel
- Ray is at (421, 439) in the dropdown overlay (from Phase 16 data)
- Scene input is a contenteditable div, not a textarea
- Aspect ratio: use "canvas" (1536×864 = 16:9 for YouTube)
- Txt2Img doesn't maintain character consistency — only CC does
- User authorized spending credits freely
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
    path = OUT_DIR / f"L{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: L{_N:02d}_{name}")


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
        if not found:
            break


def wait_for_gen_complete(page, timeout_s=120, label=""):
    """Wait for generation by watching for 'Generation Complete!' banner or new result section."""
    start = time.monotonic()

    # Track initial result count in results panel (right side)
    initial_sections = page.evaluate("""() => {
        let c = 0;
        for (const el of document.querySelectorAll('h6, [class*="header"], [class*="title"]')) {
            const text = (el.innerText || '').trim();
            const rect = el.getBoundingClientRect();
            if ((text === 'Text-to-Image' || text === 'Consistent Character' ||
                 text === 'Character Sheet' || text === 'Chat Editor') &&
                rect.x > 550 && rect.y > 60) {
                c++;
            }
        }
        return c;
    }""")

    while time.monotonic() - start < timeout_s:
        page.wait_for_timeout(5000)
        elapsed = time.monotonic() - start

        # Check for completion indicators
        state = page.evaluate("""(initial) => {
            // Check for "Generation Complete!" text
            let complete = false;
            let generating = false;
            let submitting = false;

            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Generation Complete!') complete = true;
                if (text === 'Starting a task...' || text.includes('Generating')) generating = true;
                if (text === 'Submitted!') submitting = true;
            }

            // Count current result sections
            let sections = 0;
            for (const el of document.querySelectorAll('h6, [class*="header"]')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if ((text === 'Consistent Character' || text === 'Text-to-Image' || text === 'Chat Editor') &&
                    rect.x > 550 && rect.y > 60) {
                    sections++;
                }
            }

            // Check if Generate button is clickable again
            let genReady = false;
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text.startsWith('Generate') && !text.includes('Submitted') &&
                    rect.x > 60 && rect.x < 400 && rect.y > 400 && !btn.disabled) {
                    genReady = true;
                }
            }

            return {complete, generating, submitting, sections, genReady, newSection: sections > initial};
        }""", initial_sections)

        print(f"  ... {elapsed:.0f}s {state}")

        if state.get('complete') or state.get('newSection') or (state.get('genReady') and elapsed > 15):
            print(f"  Done in {elapsed:.0f}s!")
            ss(page, f"gen_done_{label}")
            return True

    print(f"  Timed out after {timeout_s}s")
    ss(page, f"gen_timeout_{label}")
    return False


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    # Find or navigate to canvas
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

    page.set_viewport_size({"width": 1440, "height": 900})
    page.bring_to_front()
    page.wait_for_timeout(1000)
    close_all_dialogs(page)
    ss(page, "start")

    try:
        # ================================================================
        # STEP 1: Open CC panel and select Ray
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 1: SELECT RAY CHARACTER")
        print("=" * 60)

        # Click Character sidebar
        print("  Clicking Character sidebar...")
        page.mouse.click(40, 306)
        page.wait_for_timeout(1500)

        # Click "Generate Images" — this opens CC panel AND the character dropdown
        print("  Clicking 'Generate Images'...")
        page.evaluate("""() => {
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
        ss(page, "cc_with_dropdown")

        # Check if character dropdown is open (look for "Ray" text)
        ray_pos = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Ray' && rect.x > 300 && rect.x < 600 && rect.y > 100 &&
                    rect.width > 10 && rect.height > 10) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                }
            }
            return null;
        }""")
        print(f"  Ray in dropdown: {ray_pos}")

        if not ray_pos:
            # Dropdown might not be open — click "Choose a Character"
            print("  Dropdown not open, clicking 'Choose a Character'...")
            page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text === 'Choose a Character' && rect.x > 60 && rect.x < 300) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(1500)
            ss(page, "dropdown_opened")

            ray_pos = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text === 'Ray' && rect.x > 150 && rect.y > 100 &&
                        rect.width > 10 && rect.height > 10) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")
            print(f"  Ray after opening: {ray_pos}")

        if ray_pos:
            # Click Ray — click the row, not just the tiny text
            # Click at center of the row (slightly to the left of the name to hit the avatar area)
            click_x = ray_pos["x"] - 20  # Click on the avatar area left of the name
            click_y = ray_pos["y"] + ray_pos["h"] // 2
            print(f"  Clicking Ray at ({click_x}, {click_y})...")
            page.mouse.click(click_x, click_y)
            page.wait_for_timeout(2000)
            ss(page, "ray_clicked")

            # Verify selection — "Choose a Character" should now show "Ray" or similar
            selected = page.evaluate("""() => {
                // Check if the character name changed in the panel header
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 300 && rect.y > 50 && rect.y < 120 &&
                        text.length > 0 && text.length < 40 && rect.width > 50) {
                        if (text.includes('Ray') || text === 'Choose a Character') {
                            return text;
                        }
                    }
                }
                // Check if the warning "Please choose a character" is gone
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    if (text === 'Please choose a character.' && el.getBoundingClientRect().x > 60) {
                        return 'NOT_SELECTED';
                    }
                }
                return 'possibly_selected';
            }""")
            print(f"  Selection status: {selected}")
        else:
            print("  FAILED: Could not find Ray in dropdown!")
            # Map everything in the dropdown area
            dropdown_items = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 150 && rect.x < 600 && rect.y > 50 && rect.y < 500 &&
                        text.length > 0 && text.length < 40 && el.children.length < 3 &&
                        rect.width > 10) {
                        items.push({text, x: Math.round(rect.x), y: Math.round(rect.y),
                                   w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
                const seen = new Set();
                return items.filter(i => { if (seen.has(i.text)) return false; seen.add(i.text); return true; })
                           .sort((a, b) => a.y - b.y).slice(0, 20);
            }""")
            print("  Dropdown area elements:")
            for item in dropdown_items:
                print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} '{item['text']}'")

        # ================================================================
        # STEP 2: Fill scene description
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 2: FILL SCENE DESCRIPTION")
        print("=" * 60)

        # The scene input is a contenteditable div with placeholder
        # "Descreva o que você quer criar com o personagem"
        # From Phase 16 data: it's at (93,170) 238x134
        # Let's find it by looking for the "0 / 1800" counter and clicking above it

        scene_input = page.evaluate("""() => {
            // Try textarea first
            for (const el of document.querySelectorAll('textarea')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 350 && rect.width > 100 && rect.height > 20) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'textarea'};
                }
            }
            // Try contenteditable
            for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 350 && rect.width > 100 && rect.height > 20 && rect.y < 400) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'contenteditable'};
                }
            }
            // Try finding the text area by the "Character Action & Scene" label
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Character Action & Scene' && rect.x > 60 && rect.x < 350) {
                    // The input should be right below this label
                    return {x: rect.x, y: rect.y + 20, w: rect.width, h: 120, type: 'label_offset',
                            labelY: rect.y};
                }
            }
            // Try the div that contains the placeholder text
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || el.getAttribute('data-placeholder') || '').trim();
                const rect = el.getBoundingClientRect();
                if ((text.includes('Descreva') || text.includes('personagem') || text.includes('describe')) &&
                    rect.x > 60 && rect.x < 350 && rect.height > 20) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'placeholder',
                            text: text.substring(0, 50)};
                }
            }
            return null;
        }""")
        print(f"  Scene input: {scene_input}")

        if scene_input:
            # Click on the input area
            page.mouse.click(scene_input["x"] + 50, scene_input["y"] + 20)
            page.wait_for_timeout(500)

            # Clear any existing text
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(100)
            page.keyboard.press("Backspace")
            page.wait_for_timeout(200)

            scene = "Standing behind a modern desk in a minimalist studio, one hand resting on desk, confident smile, looking directly at camera, soft studio lighting, clean white background. Medium shot waist up."
            page.keyboard.type(scene, delay=5)
            page.wait_for_timeout(500)
            ss(page, "scene_typed")
            print(f"  Typed scene ({len(scene)} chars)")
        else:
            # Click directly at the known position of the textarea area
            print("  Trying direct click at known textarea position (100, 180)...")
            page.mouse.click(100, 180)
            page.wait_for_timeout(500)
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(100)
            page.keyboard.press("Backspace")
            page.wait_for_timeout(200)
            scene = "Standing in minimalist studio, confident smile, facing camera, soft lighting, white background. Medium shot."
            page.keyboard.type(scene, delay=5)
            page.wait_for_timeout(500)
            ss(page, "scene_typed_direct")

        # ================================================================
        # STEP 3: Set aspect ratio to canvas (16:9)
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 3: SET 16:9 ASPECT RATIO")
        print("=" * 60)

        # From Phase 16/17 data: Aspect Ratio buttons are at y~538
        # "canvas" button is at (224, 538) 68x24
        canvas_btn = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'canvas' && rect.x > 60 && rect.x < 350 && rect.y > 400) {
                    el.click();
                    return {x: rect.x, y: rect.y, clicked: true};
                }
            }
            return null;
        }""")
        print(f"  Canvas (16:9) button: {canvas_btn}")

        if not canvas_btn:
            # Try scrolling the panel down
            page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 100 && rect.width > 200 && rect.height > 400 &&
                        el.scrollHeight > el.clientHeight) {
                        el.scrollBy(0, 200);
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(500)

            canvas_btn = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text === 'canvas' && rect.x > 60 && rect.x < 350) {
                        el.click();
                        return {x: rect.x, y: rect.y, clicked: true};
                    }
                }
                return null;
            }""")
            print(f"  Canvas button after scroll: {canvas_btn}")

        # ================================================================
        # STEP 4: GENERATE (4 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 4: GENERATE CONSISTENT CHARACTER (4 credits)")
        print("=" * 60)

        # Check for warning
        warning = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text.startsWith('Please') && el.getBoundingClientRect().x > 60 &&
                    el.getBoundingClientRect().x < 350 && el.getBoundingClientRect().y > 600) {
                    return text;
                }
            }
            return null;
        }""")
        if warning:
            print(f"  WARNING: {warning}")

        # Find Generate button
        gen_btn = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text.includes('Generate') && rect.x > 60 && rect.x < 350 &&
                    rect.y > 400 && rect.width > 100 && !btn.disabled) {
                    return {text: text.replace(/\\n/g, ' '), x: rect.x, y: rect.y,
                            w: rect.width, h: rect.height};
                }
            }
            return null;
        }""")
        print(f"  Generate button: {gen_btn}")

        if gen_btn:
            print("  CLICKING GENERATE!")
            page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
            page.wait_for_timeout(1000)
            ss(page, "generating")

            # Wait for generation
            page.wait_for_timeout(2000)
            close_all_dialogs(page)

            success = wait_for_gen_complete(page, timeout_s=120, label="cc")
            if success:
                ss(page, "cc_result")
                print("  CC Generation succeeded!")

                # Examine the new result
                new_result = page.evaluate("""() => {
                    // Find "Consistent Character" result section
                    for (const el of document.querySelectorAll('*')) {
                        const text = (el.innerText || '').trim();
                        const rect = el.getBoundingClientRect();
                        if (text === 'Consistent Character' && rect.x > 340 && rect.y > 60) {
                            // Find the image below this header
                            const parent = el.closest('[class*="result"]') || el.parentElement?.parentElement;
                            if (parent) {
                                const img = parent.querySelector('img');
                                if (img) {
                                    const r = img.getBoundingClientRect();
                                    return {src: img.src.substring(0, 150),
                                            w: Math.round(r.width), h: Math.round(r.height)};
                                }
                            }
                        }
                    }
                    // Fallback: find newest result image
                    const imgs = [];
                    for (const img of document.querySelectorAll('img')) {
                        const r = img.getBoundingClientRect();
                        if (r.x > 340 && r.x < 1050 && r.y > 60 && r.width > 80 && r.height > 80) {
                            imgs.push({src: img.src.substring(0, 150), x: r.x, y: r.y,
                                       w: Math.round(r.width), h: Math.round(r.height)});
                        }
                    }
                    return imgs.length > 0 ? imgs[0] : null;
                }""")
                print(f"  New result: {new_result}")
        else:
            print("  Generate button not found or disabled")
            ss(page, "no_gen_btn")

            # Scroll down to find it
            page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 100 && rect.width > 200 && rect.height > 400 &&
                        el.scrollHeight > el.clientHeight) {
                        el.scrollBy(0, 300);
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(500)

            gen_btn2 = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.x > 60 && rect.x < 350 &&
                        rect.width > 100 && !btn.disabled) {
                        return {text: text.replace(/\\n/g, ' '), x: rect.x, y: rect.y,
                                w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")
            print(f"  Generate after scroll: {gen_btn2}")

            if gen_btn2:
                print("  CLICKING GENERATE!")
                page.mouse.click(gen_btn2["x"] + gen_btn2["w"]//2, gen_btn2["y"] + gen_btn2["h"]//2)
                page.wait_for_timeout(1000)
                ss(page, "generating_2")
                page.wait_for_timeout(2000)
                close_all_dialogs(page)
                success = wait_for_gen_complete(page, timeout_s=120, label="cc2")
                if success:
                    ss(page, "cc_result_2")

        # ================================================================
        # STEP 5: GENERATE ANOTHER SCENE (different pose)
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 5: GENERATE ANOTHER SCENE (holding product)")
        print("=" * 60)

        # Clear and type new scene
        scene_input2 = page.evaluate("""() => {
            for (const el of document.querySelectorAll('textarea')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 350 && rect.width > 100) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'textarea'};
                }
            }
            for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 350 && rect.width > 100 && rect.height > 20 && rect.y < 400) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'contenteditable'};
                }
            }
            return null;
        }""")

        if scene_input2:
            page.mouse.click(scene_input2["x"] + 50, scene_input2["y"] + 15)
        else:
            # Click the known position
            page.mouse.click(100, 180)

        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(100)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(200)

        scene2 = "Holding a product box in right hand, showing it to camera with enthusiastic expression, standing in modern minimalist studio, soft directional lighting, clean white background. Medium shot."
        page.keyboard.type(scene2, delay=5)
        page.wait_for_timeout(500)
        ss(page, "scene2_typed")
        print(f"  Typed scene 2 ({len(scene2)} chars)")

        # Click Generate again
        gen_btn3 = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text.includes('Generate') && rect.x > 60 && rect.x < 350 &&
                    rect.y > 400 && rect.width > 100 && !btn.disabled) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                }
            }
            return null;
        }""")

        if gen_btn3:
            print("  CLICKING GENERATE for scene 2!")
            page.mouse.click(gen_btn3["x"] + gen_btn3["w"]//2, gen_btn3["y"] + gen_btn3["h"]//2)
            page.wait_for_timeout(1000)
            ss(page, "gen2_started")
            page.wait_for_timeout(2000)
            close_all_dialogs(page)
            success = wait_for_gen_complete(page, timeout_s=120, label="cc_scene2")
            if success:
                ss(page, "cc_scene2_result")
                print("  Scene 2 generation succeeded!")

        # ================================================================
        # STEP 6: Try a WALK preset
        # ================================================================
        print("\n" + "=" * 60)
        print("  STEP 6: WALK PRESET")
        print("=" * 60)

        # Click the "Walk" preset button
        walk_btn = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Walk' && rect.x > 60 && rect.x < 200 && rect.y > 250 && rect.y < 400) {
                    el.click();
                    return {x: rect.x, y: rect.y};
                }
            }
            return null;
        }""")
        print(f"  Walk preset: {walk_btn}")

        if walk_btn:
            page.wait_for_timeout(500)
            ss(page, "walk_preset")

            # Click Generate
            gen_btn4 = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.x > 60 && rect.x < 350 &&
                        rect.y > 400 && !btn.disabled) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")
            if gen_btn4:
                print("  CLICKING GENERATE for Walk!")
                page.mouse.click(gen_btn4["x"] + gen_btn4["w"]//2, gen_btn4["y"] + gen_btn4["h"]//2)
                page.wait_for_timeout(1000)
                page.wait_for_timeout(2000)
                close_all_dialogs(page)
                success = wait_for_gen_complete(page, timeout_s=120, label="walk")
                if success:
                    ss(page, "walk_result")
                    print("  Walk generation succeeded!")

        # ================================================================
        # FINAL: Summary
        # ================================================================
        print("\n" + "=" * 60)
        print("  FINAL SUMMARY")
        print("=" * 60)

        # Count all results
        all_results = page.evaluate("""() => {
            const results = [];
            for (const el of document.querySelectorAll('h6')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.x > 340 && rect.y > 0) {
                    results.push({type: text, y: Math.round(rect.y)});
                }
            }
            return results;
        }""")
        print(f"\n  All result sections:")
        for r in all_results:
            print(f"    y={r['y']} {r['type']}")

        credits = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text.includes('Unlimited') && el.getBoundingClientRect().y < 35) {
                    return text;
                }
            }
            return 'unknown';
        }""")
        print(f"\n  Credits: {credits}")

        ss(page, "final")
        print("\n\n===== PHASE 18 COMPLETE =====")

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
