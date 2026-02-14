"""Phase 14: Actually generate images via Consistent Character, Txt2Img, and Chat Editor.

User authorized spending yellow credits freely.
Known sidebar positions from Phase 13 (1440x900 viewport).
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
    path = OUT_DIR / f"H{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: H{_N:02d}_{name}")


def close_all_dialogs(page):
    """Close popups, tutorials, previews, and other blocking overlays."""
    for _ in range(5):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip"]:
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


# Known sidebar tool positions (center of each icon area, 1440x900 viewport)
SIDEBAR = {
    "Upload": (40, 81),
    "Assets": (40, 136),
    "Txt2Img": (40, 197),
    "Img2Img": (40, 252),
    "Character": (40, 306),
    "AI Video": (40, 361),
    "Lip Sync": (40, 425),
    "Video Editor": (40, 490),
    "Motion Control": (40, 550),
    "Enhance": (40, 627),
    "Image Editor": (40, 698),
    "Instant": (40, 766),
}


def wait_for_generation(page, initial_count, timeout_s=120, label=""):
    """Wait for new images to appear in the result area."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        page.wait_for_timeout(5000)
        cur = count_results(page)
        elapsed = time.monotonic() - start
        print(f"  ... {elapsed:.0f}s ({cur} results, was {initial_count})")
        if cur > initial_count:
            print(f"  Generation complete! {cur} results in {elapsed:.0f}s")
            ss(page, f"gen_done_{label}")
            return True
    print(f"  Generation timed out after {timeout_s}s")
    ss(page, f"gen_timeout_{label}")
    return False


def count_results(page):
    """Count images in the right results area."""
    return page.evaluate("""() => {
        let c = 0;
        for (const img of document.querySelectorAll('img')) {
            const r = img.getBoundingClientRect();
            if (r.x > 900 && r.y > 80 && r.width > 40 && r.height > 40) c++;
        }
        return c;
    }""")


def map_panel(page, label=""):
    """Map visible items in the left panel (x: 60-500)."""
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


def find_and_click_text(page, text, region=None):
    """Find element by text content and click it. Returns position or None."""
    region = region or {}
    result = page.evaluate("""({text, region}) => {
        const minX = region.minX || 0, maxX = region.maxX || 9999;
        const minY = region.minY || 0, maxY = region.maxY || 9999;
        for (const el of document.querySelectorAll('*')) {
            const t = (el.innerText || '').trim();
            const rect = el.getBoundingClientRect();
            if (t === text && rect.x >= minX && rect.x <= maxX && rect.y >= minY && rect.y <= maxY
                && rect.width > 0 && rect.height > 0 && el.children.length < 5) {
                el.click();
                return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
            }
        }
        return null;
    }""", {"text": text, "region": region})
    if result:
        print(f"  Clicked '{text}' at ({result['x']},{result['y']})")
    else:
        print(f"  '{text}' not found")
    return result


def find_element(page, text, region=None):
    """Find element by text without clicking."""
    region = region or {}
    return page.evaluate("""({text, region}) => {
        const minX = region.minX || 0, maxX = region.maxX || 9999;
        const minY = region.minY || 0, maxY = region.maxY || 9999;
        for (const el of document.querySelectorAll('*')) {
            const t = (el.innerText || '').trim();
            const rect = el.getBoundingClientRect();
            if (t.includes(text) && rect.x >= minX && rect.x <= maxX && rect.y >= minY && rect.y <= maxY
                && rect.width > 0 && rect.height > 0 && el.children.length < 5) {
                return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, fullText: t.substring(0, 80)};
            }
        }
        return null;
    }""", {"text": text, "region": region})


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    # Find or open canvas page
    page = None
    for p in context.pages:
        if "canvas?id=19797967" in p.url:
            page = p
            break

    if not page:
        page = context.new_page()
        page.goto("https://www.dzine.ai/canvas?id=19797967",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

    # CRITICAL: Set viewport
    page.set_viewport_size({"width": 1440, "height": 900})
    page.bring_to_front()
    page.wait_for_timeout(2000)

    # Close all blocking dialogs
    close_all_dialogs(page)
    page.wait_for_timeout(1000)
    ss(page, "start")

    try:
        # ================================================================
        # PART 1: CONSISTENT CHARACTER GENERATION (4 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 1: CONSISTENT CHARACTER — Generate Ray Image")
        print("=" * 60)

        # Click Character in sidebar
        print("\n  Clicking Character sidebar...")
        page.mouse.click(*SIDEBAR["Character"])
        page.wait_for_timeout(2000)
        close_all_dialogs(page)
        ss(page, "character_panel")
        panel_items = map_panel(page, "Character Panel")

        # Look for "Generate Images" button in the panel
        print("\n  Looking for 'Generate Images'...")
        gen_img = find_and_click_text(page, "Generate Images", {"minX": 60, "maxX": 500})
        if not gen_img:
            # Try partial match
            for item in panel_items:
                if "Generate" in item["text"] and "Image" in item["text"]:
                    page.mouse.click(item["x"] + item["w"] // 2, item["y"] + item["h"] // 2)
                    print(f"  Clicked panel item: {item['text']}")
                    break

        page.wait_for_timeout(2000)
        close_all_dialogs(page)
        ss(page, "consistent_char_panel")
        cc_items = map_panel(page, "Consistent Character Panel")

        # Find the textarea for action/scene description
        textarea_info = page.evaluate("""() => {
            // Look for textarea or contenteditable in the panel
            for (const el of document.querySelectorAll('textarea, [contenteditable="true"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 20) {
                    return {tag: el.tagName, x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                            placeholder: el.placeholder || el.getAttribute('data-placeholder') || '',
                            type: el.contentEditable === 'true' ? 'contenteditable' : 'textarea'};
                }
            }
            return null;
        }""")
        print(f"\n  Textarea: {textarea_info}")

        if textarea_info:
            # Click and type scene description
            page.mouse.click(textarea_info["x"] + 50, textarea_info["y"] + 10)
            page.wait_for_timeout(300)

            scene = "Standing behind a modern desk in a minimalist studio, one hand resting on desk, confident smile, looking at camera, soft studio lighting, clean white background"
            if textarea_info["type"] == "textarea":
                page.fill(f'textarea', scene)
            else:
                page.keyboard.type(scene, delay=5)
            page.wait_for_timeout(500)
            ss(page, "cc_typed_scene")
            print(f"  Typed scene description ({len(scene)} chars)")
        else:
            print("  No textarea found — trying to find input area via panel items")
            # Look for "Character Action & Scene" label then find next input
            for i, item in enumerate(cc_items):
                if "Action" in item["text"] or "Scene" in item["text"]:
                    # Click below this label
                    page.mouse.click(item["x"] + 50, item["y"] + 40)
                    page.wait_for_timeout(300)
                    scene = "Standing in minimalist studio, confident smile, looking at camera, soft lighting"
                    page.keyboard.type(scene, delay=5)
                    page.wait_for_timeout(500)
                    ss(page, "cc_typed_scene")
                    break

        # Count current results before generating
        initial = count_results(page)
        print(f"\n  Current results: {initial}")

        # Click Generate button
        print("  Looking for Generate button...")
        gen_btn = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text.includes('Generate') && rect.x > 60 && rect.x < 500 &&
                    rect.width > 50 && !btn.disabled) {
                    return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                            w: rect.width, h: rect.height, disabled: btn.disabled};
                }
            }
            return null;
        }""")
        print(f"  Generate button: {gen_btn}")

        if gen_btn:
            page.mouse.click(gen_btn["x"] + gen_btn["w"] // 2, gen_btn["y"] + gen_btn["h"] // 2)
            page.wait_for_timeout(1000)
            ss(page, "cc_generating")
            print("  Clicked Generate! Waiting for result...")

            # Check for any error/popup
            page.wait_for_timeout(2000)
            close_all_dialogs(page)

            success = wait_for_generation(page, initial, timeout_s=90, label="cc")

            if success:
                # Get info about the generated image
                new_count = count_results(page)
                print(f"  Total results now: {new_count}")

                # Try to download the latest result
                result_info = page.evaluate("""() => {
                    const imgs = [];
                    for (const img of document.querySelectorAll('img')) {
                        const r = img.getBoundingClientRect();
                        if (r.x > 900 && r.y > 80 && r.width > 40 && r.height > 40) {
                            imgs.push({src: img.src.substring(0, 100), x: r.x, y: r.y,
                                       w: Math.round(r.width), h: Math.round(r.height)});
                        }
                    }
                    return imgs;
                }""")
                print(f"  Result images:")
                for img in result_info:
                    print(f"    ({img['x']:.0f},{img['y']:.0f}) {img['w']}x{img['h']} {img['src']}")
        else:
            print("  Generate button not found. Checking panel state...")
            ss(page, "cc_no_generate")

        # Close Consistent Character panel before next test
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # ================================================================
        # PART 2: TXT2IMG GENERATION (20 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 2: TXT2IMG — Generate Ray Image")
        print("=" * 60)

        # Click Txt2Img in sidebar
        print("\n  Clicking Txt2Img sidebar...")
        page.mouse.click(*SIDEBAR["Txt2Img"])
        page.wait_for_timeout(2000)
        close_all_dialogs(page)
        ss(page, "txt2img_panel")
        t2i_items = map_panel(page, "Txt2Img Panel")

        # Find the prompt textarea
        prompt_info = page.evaluate("""() => {
            for (const el of document.querySelectorAll('textarea')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 30) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                            placeholder: el.placeholder || '', maxLength: el.maxLength};
                }
            }
            // Try contenteditable
            for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 30) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'contenteditable'};
                }
            }
            return null;
        }""")
        print(f"\n  Prompt input: {prompt_info}")

        if prompt_info:
            page.mouse.click(prompt_info["x"] + 50, prompt_info["y"] + 15)
            page.wait_for_timeout(300)

            # Clear any existing text
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(100)

            prompt = "Ray, young adult male YouTuber, light skin, short dark hair, wearing charcoal gray t-shirt. Standing in modern minimalist studio with soft lighting, clean white background. Medium shot waist up, natural confident smile, facing camera directly. Photorealistic, 4K quality, professional studio portrait."
            page.keyboard.type(prompt, delay=3)
            page.wait_for_timeout(500)
            ss(page, "txt2img_typed")
            print(f"  Typed prompt ({len(prompt)} chars)")

            # Check current settings (style, quality, ratio)
            settings = page.evaluate("""() => {
                const info = {};
                // Find selected style
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 500) {
                        if (text.includes('Nano') || text.includes('Banana') || text.includes('Pro')) {
                            if (rect.width > 50 && rect.height < 50 && rect.y > 50 && rect.y < 200) {
                                info.style = text.substring(0, 40);
                            }
                        }
                        if (text === '2K' || text === '4K' || text === '1K') {
                            info.quality = text;
                        }
                    }
                }
                return info;
            }""")
            print(f"  Settings: {settings}")

            # Count results before generating
            initial = count_results(page)

            # Click Generate
            gen_btn = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.x > 60 && rect.x < 500 &&
                        rect.width > 50 && !btn.disabled) {
                        return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                                w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")
            print(f"\n  Generate button: {gen_btn}")

            if gen_btn:
                page.mouse.click(gen_btn["x"] + gen_btn["w"] // 2, gen_btn["y"] + gen_btn["h"] // 2)
                page.wait_for_timeout(1000)
                ss(page, "txt2img_generating")
                print("  Clicked Generate! Waiting...")

                page.wait_for_timeout(2000)
                close_all_dialogs(page)

                success = wait_for_generation(page, initial, timeout_s=120, label="txt2img")
                if success:
                    print(f"  Results: {count_results(page)}")
            else:
                print("  Generate button not found")
                ss(page, "txt2img_no_gen")
        else:
            print("  Prompt input not found")

        # Close Txt2Img panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # ================================================================
        # PART 3: CHAT EDITOR GENERATION (20 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 3: CHAT EDITOR — Generate Ray Image")
        print("=" * 60)

        # The chat editor is at the bottom of the canvas
        # From Phase 13: prompt textarea at (408,784) with 632x40 dimensions
        # But first, click the chat bar to expand it

        # Click empty area first to deselect any layer
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Look for the chat editor bar at the bottom
        chat_bar = page.evaluate("""() => {
            // Look for the chat input area at the bottom
            for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 600 && rect.width > 100 && rect.height > 10) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                            visible: rect.width > 50, type: 'contenteditable'};
                }
            }
            // Try textarea
            for (const el of document.querySelectorAll('textarea')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 600 && rect.width > 100) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                            visible: true, type: 'textarea'};
                }
            }
            // Try clicking the collapsed bar area
            return null;
        }""")
        print(f"\n  Chat bar: {chat_bar}")

        if not chat_bar or not chat_bar.get("visible"):
            # Click the bottom area to expand chat
            print("  Chat bar not visible, clicking bottom area...")
            page.mouse.click(700, 860)
            page.wait_for_timeout(1500)
            close_all_dialogs(page)

            # Try again
            chat_bar = page.evaluate("""() => {
                for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.y > 600 && rect.width > 100 && rect.height > 10) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                visible: rect.width > 50, type: 'contenteditable'};
                    }
                }
                for (const el of document.querySelectorAll('textarea')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.y > 600 && rect.width > 100) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                visible: true, type: 'textarea'};
                    }
                }
                return null;
            }""")
            print(f"  Chat bar after click: {chat_bar}")
            ss(page, "chat_expanded")

        if chat_bar and chat_bar.get("visible"):
            # Click the prompt area
            page.mouse.click(chat_bar["x"] + 50, chat_bar["y"] + chat_bar["h"] // 2)
            page.wait_for_timeout(300)

            prompt = "Ray, young adult male YouTuber with light skin and short dark hair, wearing a charcoal gray t-shirt. He is standing in a clean modern studio holding a product in his right hand, showing it to the camera with an enthusiastic expression. The background is minimalist white with subtle soft lighting. Medium shot from the waist up. Photorealistic, professional YouTube thumbnail quality, 4K."
            page.keyboard.type(prompt, delay=3)
            page.wait_for_timeout(500)
            ss(page, "chat_typed")
            print(f"  Typed prompt ({len(prompt)} chars)")

            # Count before generating
            initial = count_results(page)

            # Click Generate button (at the right end of the chat bar)
            gen_btn = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.y > 600 && !btn.disabled) {
                        return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                                w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")
            print(f"\n  Generate button: {gen_btn}")

            if gen_btn:
                page.mouse.click(gen_btn["x"] + gen_btn["w"] // 2, gen_btn["y"] + gen_btn["h"] // 2)
                page.wait_for_timeout(1000)
                ss(page, "chat_generating")
                print("  Clicked Generate! Waiting...")

                page.wait_for_timeout(2000)
                close_all_dialogs(page)

                success = wait_for_generation(page, initial, timeout_s=120, label="chat")
                if success:
                    print(f"  Results: {count_results(page)}")
            else:
                print("  Generate button not found in chat area")
                # Map all buttons near bottom
                bottom_btns = page.evaluate("""() => {
                    const btns = [];
                    for (const btn of document.querySelectorAll('button')) {
                        const rect = btn.getBoundingClientRect();
                        if (rect.y > 600 && rect.width > 20 && rect.height > 20) {
                            btns.push({text: (btn.innerText || '').trim().substring(0, 30),
                                       x: Math.round(rect.x), y: Math.round(rect.y),
                                       w: Math.round(rect.width), h: Math.round(rect.height),
                                       disabled: btn.disabled});
                        }
                    }
                    return btns;
                }""")
                print("  Bottom buttons:")
                for b in bottom_btns:
                    print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} '{b['text']}' disabled={b['disabled']}")
        else:
            print("  Chat editor not accessible")
            # Take a screenshot of the full bottom area
            ss(page, "chat_not_found")

            # Map everything at the bottom
            bottom_area = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.y > 700 && rect.y < 900 && rect.x > 200 && rect.x < 1200 &&
                        rect.width > 30 && rect.height > 10 && el.children.length < 3) {
                        const text = (el.innerText || '').trim();
                        const cls = (el.className || '').toString().substring(0, 30);
                        if (text || cls) {
                            items.push({text: text.substring(0, 50), tag: el.tagName, cls,
                                       x: Math.round(rect.x), y: Math.round(rect.y),
                                       w: Math.round(rect.width), h: Math.round(rect.height)});
                        }
                    }
                }
                return items.sort((a, b) => a.y - b.y).slice(0, 20);
            }""")
            print("  Bottom area elements:")
            for item in bottom_area:
                print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> [{item['cls'][:15]}] {item['text']}")

        # ================================================================
        # PART 4: EXAMINE ALL GENERATED RESULTS
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 4: EXAMINE RESULTS")
        print("=" * 60)

        total = count_results(page)
        print(f"\n  Total result images: {total}")

        # Get all result image URLs and positions
        all_results = page.evaluate("""() => {
            const results = [];
            for (const img of document.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.x > 900 && r.y > 80 && r.width > 40 && r.height > 40) {
                    results.push({
                        src: img.src,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        alt: (img.alt || '').substring(0, 50)
                    });
                }
            }
            return results;
        }""")
        print(f"\n  Result images ({len(all_results)}):")
        for i, img in enumerate(all_results):
            print(f"    [{i}] ({img['x']},{img['y']}) {img['w']}x{img['h']} alt='{img['alt']}'")
            print(f"        src: {img['src'][:120]}")

        # Click on the first/latest result to see action buttons
        if all_results:
            latest = all_results[-1]
            page.mouse.click(latest["x"] + latest["w"] // 2, latest["y"] + latest["h"] // 2)
            page.wait_for_timeout(1500)
            ss(page, "result_preview")

            # Map the preview overlay / action buttons
            actions = page.evaluate("""() => {
                const items = [];
                for (const btn of document.querySelectorAll('button, [role="button"]')) {
                    const rect = btn.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const text = (btn.innerText || btn.title || btn.getAttribute('aria-label') || '').trim();
                        const svg = btn.querySelector('svg') ? true : false;
                        if (text || svg) {
                            items.push({text: text.substring(0, 40), x: Math.round(rect.x),
                                       y: Math.round(rect.y), w: Math.round(rect.width),
                                       h: Math.round(rect.height), svg});
                        }
                    }
                }
                return items;
            }""")
            print(f"\n  Action buttons after clicking result:")
            for a in actions:
                print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} '{a['text']}' svg={a['svg']}")

        # ================================================================
        # PART 5: CREDIT BALANCE CHECK
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 5: CREDIT BALANCE")
        print("=" * 60)

        credits = page.evaluate("""() => {
            const info = {};
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    // Look for credit numbers (usually in header area)
                    if (/^\\d{1,6}$/.test(text) && rect.y < 50) {
                        info[`credits_${Math.round(rect.x)}`] = text;
                    }
                    // Look for credit labels
                    if ((text.includes('credit') || text.includes('Credit')) && rect.y < 80) {
                        info.label = text.substring(0, 60);
                    }
                }
            }
            return info;
        }""")
        print(f"  Credits info: {credits}")

        # Also check the top-right area for user/credit info
        top_right = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 1200 && rect.y < 50 && rect.width > 5 && rect.height > 5 &&
                    el.children.length < 3) {
                    const text = (el.innerText || '').trim();
                    if (text && text.length < 40) {
                        items.push({text, x: Math.round(rect.x), y: Math.round(rect.y)});
                    }
                }
            }
            const seen = new Set();
            return items.filter(i => { if (seen.has(i.text)) return false; seen.add(i.text); return true; });
        }""")
        print(f"\n  Top-right elements:")
        for item in top_right:
            print(f"    ({item['x']},{item['y']}) '{item['text']}'")

        ss(page, "final_state")
        print("\n\n===== PHASE 14 COMPLETE =====")

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
