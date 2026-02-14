"""Phase 10: Generate Ray image, place on canvas, then explore all layer-dependent tools.

Most Dzine tools require a layer (image) on the canvas. This phase:
1. Generates a Ray image via Consistent Character (4 credits)
2. Places result on canvas as a layer
3. Then explores: Img2Img, Lip Sync, AI Video, Enhance, Image Editor, etc.
4. Also tests the Chat Editor (bottom bar) for general generation
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

_SS_COUNT = 0


def ss(page, name):
    global _SS_COUNT
    _SS_COUNT += 1
    path = OUT_DIR / f"D{_SS_COUNT:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: D{_SS_COUNT:02d}_{name}")


def close_popup(page):
    for _ in range(3):
        try:
            btn = page.locator('button:has-text("Not now")')
            if btn.count() > 0 and btn.first.is_visible(timeout=1500):
                btn.first.click()
                page.wait_for_timeout(500)
        except Exception:
            break


def click_sidebar(page, tool_name):
    """Click sidebar tool by name."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    clicked = page.evaluate("""(name) => {
        for (const el of document.querySelectorAll('*')) {
            const rect = el.getBoundingClientRect();
            const text = (el.innerText || '').trim().replace(/\\n/g, ' ');
            if (rect.x >= 0 && rect.x < 65 && rect.width > 10 && rect.width < 70 &&
                rect.height > 10 && rect.y > 50) {
                if (text === name || text.startsWith(name + ' ') || text.startsWith(name + '\\n') || text === name.replace(' ', '\\n')) {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }""", tool_name)
    if clicked:
        page.wait_for_timeout(2000)
    return clicked


def close_panel(page):
    """Close any open left panel."""
    # Try clicking the X button in the panel header area
    page.evaluate("""() => {
        // Find clickable elements that look like close buttons in the panel header
        for (const el of document.querySelectorAll('svg, button, [class*="close"], [class*="icon"]')) {
            const rect = el.getBoundingClientRect();
            if (rect.x > 295 && rect.x < 340 && rect.y > 50 && rect.y < 90 &&
                rect.width < 40 && rect.height < 40 && rect.width > 5) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)


def map_panel(page, label=""):
    """Map visible items in the left panel."""
    items = page.evaluate("""() => {
        const items = [];
        const seen = new Set();
        for (const el of document.querySelectorAll('*')) {
            const rect = el.getBoundingClientRect();
            if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                rect.width > 15 && rect.height > 5) {
                const text = (el.innerText || '').trim();
                if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                    seen.add(text);
                    items.push({text: text.substring(0, 80), tag: el.tagName,
                                cls: (el.className || '').toString().substring(0, 30), y: Math.round(rect.y)});
                }
            }
        }
        return items.sort((a, b) => a.y - b.y).slice(0, 40);
    }""")
    print(f"\n  {label} ({len(items)} items):")
    for item in items:
        print(f"    y={item['y']} <{item['tag']}> [{item['cls']}] {item['text']}")
    return items


def count_results(page):
    """Count result images in right panel."""
    return page.evaluate("""() => {
        let count = 0;
        for (const img of document.querySelectorAll('img')) {
            const rect = img.getBoundingClientRect();
            if (rect.x > 1050 && rect.y > 80 && rect.width > 50 && rect.height > 50) count++;
        }
        return count;
    }""")


def wait_for_generation(page, initial_count, max_wait_s=120):
    """Wait until new results appear in the right panel."""
    start = time.monotonic()
    while time.monotonic() - start < max_wait_s:
        page.wait_for_timeout(3000)
        current = count_results(page)
        elapsed = time.monotonic() - start
        if current > initial_count:
            print(f"  Generation complete! {current} results (was {initial_count}) in {elapsed:.0f}s")
            return True
        if int(elapsed) % 15 == 0 and elapsed > 5:
            print(f"  ... waiting {elapsed:.0f}s (results: {current})")
    print(f"  Generation timed out after {max_wait_s}s")
    return False


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    # Find canvas page
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
        page.wait_for_timeout(5000)

    page.bring_to_front()
    page.wait_for_timeout(2000)
    close_popup(page)
    ss(page, "start")

    try:
        # ===== PART A: Generate Ray image via Consistent Character =====
        print("\n" + "="*60)
        print("PART A: GENERATE RAY IMAGE (Consistent Character)")
        print("="*60)

        # Step 1: Click Character sidebar
        if not click_sidebar(page, "Character"):
            print("  ERROR: Cannot find Character sidebar")
            return

        ss(page, "character_panel")

        # Step 2: Click "Generate Images" in the left panel
        gen_clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 400 && rect.width > 50 && rect.height > 20 &&
                    (el.innerText || '').trim().startsWith('Generate Images')) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if gen_clicked:
            page.wait_for_timeout(3000)
            print("  Opened 'Generate Images' (Consistent Character)")
            ss(page, "consistent_char")
        else:
            print("  'Generate Images' not found — trying direct panel")

        # Step 3: Check that Ray is already selected as character
        ray_check = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Ray' && rect.x > 60 && rect.x < 400 && rect.y > 80 && rect.y < 200) {
                    return true;
                }
            }
            return false;
        }""")
        print(f"  Ray selected: {ray_check}")

        # Step 4: Read current scene/action text
        scene_text = page.evaluate("""() => {
            const textareas = document.querySelectorAll('textarea');
            for (const ta of textareas) {
                const rect = ta.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 400 && rect.y > 200) {
                    return {value: ta.value.substring(0, 200), y: rect.y, placeholder: ta.placeholder};
                }
            }
            return null;
        }""")
        print(f"  Scene textarea: {scene_text}")

        # Step 5: Set a new scene description for Ray
        new_scene = "Ray standing in a modern studio, facing the camera, confident smile, arms crossed. Clean white background with soft studio lighting. Photorealistic. Clean. Stable. Medium shot, waist up. Suitable for AI lipsync."

        page.evaluate("""(text) => {
            const textareas = document.querySelectorAll('textarea');
            for (const ta of textareas) {
                const rect = ta.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 400 && rect.y > 250 && rect.y < 600) {
                    ta.value = text;
                    ta.dispatchEvent(new Event('input', {bubbles: true}));
                    ta.dispatchEvent(new Event('change', {bubbles: true}));
                    return true;
                }
            }
            return false;
        }""", new_scene)
        page.wait_for_timeout(1000)
        ss(page, "scene_set")

        # Step 6: Set 16:9 aspect ratio
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === '16:9' && rect.x > 60 && rect.x < 400) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Step 7: Set Normal generation mode
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text === 'Normal' && rect.x > 60 && rect.x < 400 && rect.y > 700) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Step 8: Count initial results
        initial = count_results(page)
        print(f"  Initial result count: {initial}")

        # Step 9: Click Generate
        print("  Clicking Generate...")
        gen_result = page.evaluate("""() => {
            // Find the generate button in the left panel area
            for (const btn of document.querySelectorAll('button')) {
                const rect = btn.getBoundingClientRect();
                const text = (btn.innerText || '').trim();
                if (rect.x > 60 && rect.x < 400 && rect.y > 700 && text.startsWith('Generate')) {
                    btn.click();
                    return {clicked: true, text, y: rect.y};
                }
            }
            return {clicked: false};
        }""")
        print(f"  Generate click: {gen_result}")

        if gen_result.get("clicked"):
            ss(page, "generating")

            # Step 10: Wait for generation
            if wait_for_generation(page, initial, max_wait_s=120):
                ss(page, "generation_done")

                # Step 11: Place result on canvas — click the first new result image
                print("\n  Placing result on canvas...")
                placed = page.evaluate("""() => {
                    const imgs = [];
                    for (const img of document.querySelectorAll('img')) {
                        const rect = img.getBoundingClientRect();
                        if (rect.x > 1050 && rect.y > 80 && rect.width > 50) {
                            imgs.push(img);
                        }
                    }
                    if (imgs.length > 0) {
                        // Click the first result image
                        imgs[0].click();
                        return true;
                    }
                    return false;
                }""")
                page.wait_for_timeout(3000)
                ss(page, "result_placed")

                # Check if canvas now has layers
                layers = page.evaluate("""() => {
                    const canvas = document.querySelector('#canvas');
                    const layers = document.querySelectorAll('[class*="layer"]');
                    return {canvasFound: !!canvas, layerCount: layers.length};
                }""")
                print(f"  Canvas state: {layers}")

        # ===== PART B: Now explore tools that need a layer =====
        print("\n" + "="*60)
        print("PART B: EXPLORING TOOLS WITH LAYER ON CANVAS")
        print("="*60)

        # Close any panel first
        close_panel(page)
        page.wait_for_timeout(1000)

        # B1: Txt2Img
        print("\n--- B1: Txt2Img ---")
        if click_sidebar(page, "Txt2Img"):
            page.wait_for_timeout(1500)
            ss(page, "txt2img_with_layer")
            map_panel(page, "Txt2Img with layer")

        close_panel(page)

        # B2: Img2Img
        print("\n--- B2: Img2Img ---")
        if click_sidebar(page, "Img2Img"):
            page.wait_for_timeout(1500)
            ss(page, "img2img_with_layer")
            map_panel(page, "Img2Img with layer")

        close_panel(page)

        # B3: Lip Sync
        print("\n--- B3: Lip Sync ---")
        if click_sidebar(page, "Lip Sync"):
            page.wait_for_timeout(1500)
            ss(page, "lip_sync_with_layer")
            map_panel(page, "Lip Sync with layer")

        close_panel(page)

        # B4: AI Video
        print("\n--- B4: AI Video ---")
        if click_sidebar(page, "AI Video"):
            page.wait_for_timeout(1500)
            ss(page, "ai_video_with_layer")
            map_panel(page, "AI Video with layer")

        close_panel(page)

        # B5: Enhance & Upscale
        print("\n--- B5: Enhance & Upscale ---")
        page.evaluate("""() => {
            const sidebar = document.querySelector('[class*="tool-list"]');
            if (sidebar) sidebar.scrollTop = sidebar.scrollHeight;
        }""")
        page.wait_for_timeout(300)
        if click_sidebar(page, "Enhance"):
            page.wait_for_timeout(1500)
            ss(page, "enhance_with_layer")
            map_panel(page, "Enhance with layer")

        close_panel(page)

        # B6: Image Editor
        print("\n--- B6: Image Editor ---")
        if click_sidebar(page, "Image Editor"):
            page.wait_for_timeout(1500)
            ss(page, "image_editor_with_layer")
            map_panel(page, "Image Editor with layer")

        close_panel(page)

        # B7: Video Editor
        print("\n--- B7: Video Editor ---")
        if click_sidebar(page, "Video Editor"):
            page.wait_for_timeout(1500)
            ss(page, "video_editor_with_layer")
            map_panel(page, "Video Editor with layer")

        close_panel(page)

        # B8: Motion Control
        print("\n--- B8: Motion Control ---")
        if click_sidebar(page, "Motion Control"):
            page.wait_for_timeout(1500)
            ss(page, "motion_control_with_layer")
            map_panel(page, "Motion Control with layer")

        close_panel(page)

        # Scroll sidebar back to top
        page.evaluate("""() => {
            const sidebar = document.querySelector('[class*="tool-list"]');
            if (sidebar) sidebar.scrollTop = 0;
        }""")

        # B9: Upload tool
        print("\n--- B9: Upload ---")
        if click_sidebar(page, "Upload"):
            page.wait_for_timeout(1500)
            ss(page, "upload_with_layer")
            map_panel(page, "Upload with layer")

        close_panel(page)

        # B10: Assets
        print("\n--- B10: Assets ---")
        if click_sidebar(page, "Assets"):
            page.wait_for_timeout(1500)
            ss(page, "assets_with_layer")
            map_panel(page, "Assets with layer")

        close_panel(page)

        # ===== PART C: Top Processing Tools =====
        print("\n" + "="*60)
        print("PART C: TOP PROCESSING TOOLS (with layer)")
        print("="*60)

        for tool_name in ["AI Eraser", "Hand Repair", "Expression", "BG Remove"]:
            print(f"\n--- {tool_name} ---")
            clicked = page.evaluate("""(name) => {
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    if (text === name && rect.y > 70 && rect.y < 120 && rect.x > 350 && rect.x < 1000) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""", tool_name)
            if clicked:
                page.wait_for_timeout(1500)
                ss(page, tool_name.replace(" ", "_").lower())
                map_panel(page, tool_name)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

        # ===== PART D: Test Chat Editor =====
        print("\n" + "="*60)
        print("PART D: CHAT EDITOR TEST")
        print("="*60)

        close_panel(page)
        page.wait_for_timeout(1000)

        # Click the collapsed chat bar to expand it
        chat_bar = page.locator('[class*="chat-editor-bar"]')
        if chat_bar.count() > 0:
            try:
                chat_bar.first.click(timeout=3000)
                page.wait_for_timeout(1500)
                ss(page, "chat_expanded")
            except Exception:
                pass

        # Find and map the expanded chat editor
        chat_info = page.evaluate("""() => {
            const items = {};

            // Prompt area
            const prompt = document.querySelector('[contenteditable="true"].custom-textarea');
            if (prompt) {
                const rect = prompt.getBoundingClientRect();
                items.prompt = {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                               placeholder: prompt.getAttribute('data-placeholder') || ''};
            }

            // Model button
            const model_btn = document.querySelector('button.option-btn');
            if (model_btn) {
                items.model = (model_btn.innerText || '').trim();
            }

            // Generate button
            const gen = document.querySelector('#chat-editor-generate-btn');
            if (gen) {
                const rect = gen.getBoundingClientRect();
                items.generate = {x: rect.x, y: rect.y, text: (gen.innerText || '').trim(),
                                  disabled: gen.disabled};
            }

            // Reference upload button
            const ref = document.querySelector('button.upload-image-btn');
            if (ref) {
                items.ref_upload = true;
            }

            return items;
        }""")
        print(f"\n  Chat editor state: {json.dumps(chat_info, indent=2)}")

        # Check current model
        if chat_info.get("model"):
            print(f"\n  Current model: {chat_info['model']}")

        # Try clicking model selector to see options
        model_clicked = page.evaluate("""() => {
            const btn = document.querySelector('button.option-btn');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        if model_clicked:
            page.wait_for_timeout(1000)
            ss(page, "model_selector")

            # Map model options
            models = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('.option-item, [class*="option-item"]')) {
                    const text = (el.innerText || '').trim();
                    const active = el.classList.contains('active');
                    if (text) items.push({text, active});
                }
                return items;
            }""")
            print(f"\n  Available models:")
            for m in models:
                active = " (ACTIVE)" if m['active'] else ""
                print(f"    {m['text']}{active}")

            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # ===== PART E: Test result action buttons =====
        print("\n" + "="*60)
        print("PART E: RESULT ACTION BUTTONS")
        print("="*60)

        # Find result images and their actions
        result_actions = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('[class*="gen-handle-func"]')) {
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (rect.x > 1050 && rect.width > 50 && text) {
                    items.push({text: text.substring(0, 40), y: Math.round(rect.y)});
                }
            }
            return items.sort((a, b) => a.y - b.y);
        }""")
        print(f"\n  Result action buttons ({len(result_actions)}):")
        for ra in result_actions:
            print(f"    y={ra['y']}: {ra['text']}")

        # ===== PART F: Canvas Size Aspect Ratios =====
        print("\n" + "="*60)
        print("PART F: CANVAS ASPECT RATIO OPTIONS")
        print("="*60)

        # Click the size indicator
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (rect.y < 50 && rect.x > 50 && rect.x < 250 && (text.includes('×') || text.includes('x'))) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        ss(page, "size_dialog")

        # Map all size/ratio options
        size_full = page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (rect.width > 20 && rect.height > 10 && text && text.length < 80 && !seen.has(text)) {
                    const cls = (el.className || '').toString().substring(0, 30);
                    if (text.includes(':') || text.includes('×') || text.includes('Custom') ||
                        text.includes('Apply') || text.includes('Cancel') || text.includes('Width') ||
                        text.includes('Height') || cls.includes('ratio') || cls.includes('size')) {
                        seen.add(text);
                        items.push({text, cls, y: Math.round(rect.y), x: Math.round(rect.x)});
                    }
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 20);
        }""")
        for s in size_full:
            print(f"    ({s['x']},{s['y']}) [{s['cls'][:15]}] {s['text']}")

        # Cancel the dialog
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Cancel')) { btn.click(); return; }
            }
        }""")
        page.wait_for_timeout(500)

        print("\n\n" + "="*60)
        print("PHASE 10 COMPLETE")
        print("="*60)

    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        if should_close:
            context.close()
        pw.stop()


if __name__ == "__main__":
    main()
