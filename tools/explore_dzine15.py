"""Phase 15: Exit AI Eraser mode, then generate images.

The canvas was stuck in AI Eraser mode from Phase 13's top-bar tool exploration.
Must click "Exit" first to restore the normal canvas with sidebar.
Credits: Unlimited (green) + 9,000 (purple video credits).
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
    path = OUT_DIR / f"I{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: I{_N:02d}_{name}")


def close_all_dialogs(page):
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


def count_results(page):
    return page.evaluate("""() => {
        let c = 0;
        for (const img of document.querySelectorAll('img')) {
            const r = img.getBoundingClientRect();
            if (r.x > 1050 && r.y > 80 && r.width > 40 && r.height > 40) c++;
        }
        return c;
    }""")


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


def verify_sidebar(page):
    """Verify left sidebar icons are visible at x < 80."""
    items = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const rect = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (rect.x >= 0 && rect.x < 80 && rect.y > 40 && rect.width > 10 &&
                text.length > 2 && text.length < 30 && el.children.length < 3) {
                items.push({text, x: Math.round(rect.x), y: Math.round(rect.y),
                           w: Math.round(rect.width), h: Math.round(rect.height)});
            }
        }
        const seen = new Set();
        return items.filter(i => { if (seen.has(i.text)) return false; seen.add(i.text); return true; })
                   .sort((a, b) => a.y - b.y);
    }""")
    return items


def wait_for_generation(page, initial_count, timeout_s=120, label=""):
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


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

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

    page.set_viewport_size({"width": 1440, "height": 900})
    page.bring_to_front()
    page.wait_for_timeout(1000)

    try:
        # ============================================================
        # STEP 0: EXIT AI ERASER MODE
        # ============================================================
        print("\n===== STEP 0: EXIT AI ERASER MODE =====")

        # Check if we're in AI Eraser mode
        eraser_mode = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'AI Eraser' && rect.y < 30 && rect.x > 200 && rect.x < 500) {
                    return true;
                }
            }
            return false;
        }""")
        print(f"  In AI Eraser mode: {eraser_mode}")

        if eraser_mode:
            # Click the "Exit" button
            exit_btn = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text === 'Exit' && rect.y < 30) {
                        btn.click();
                        return {x: rect.x, y: rect.y};
                    }
                }
                return null;
            }""")
            print(f"  Clicked Exit: {exit_btn}")
            page.wait_for_timeout(2000)
        else:
            # Try Escape to exit any mode
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

        close_all_dialogs(page)
        page.wait_for_timeout(1000)
        ss(page, "after_exit")

        # Verify sidebar is back
        sidebar = verify_sidebar(page)
        print(f"\n  Sidebar items ({len(sidebar)}):")
        for s in sidebar:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text']}'")

        if not sidebar:
            print("  Sidebar still not visible — reloading page...")
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            close_all_dialogs(page)
            page.wait_for_timeout(1000)

            sidebar = verify_sidebar(page)
            print(f"\n  Sidebar after reload ({len(sidebar)}):")
            for s in sidebar:
                print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text']}'")

        if not sidebar:
            print("  FATAL: Sidebar not visible after reload. Cannot continue.")
            ss(page, "no_sidebar")
            return

        # Build sidebar position map
        sidebar_pos = {}
        for s in sidebar:
            sidebar_pos[s['text']] = (s['x'] + s['w']//2, s['y'] + s['h']//2)
        print(f"\n  Sidebar position map: {list(sidebar_pos.keys())}")

        ss(page, "normal_canvas")

        # ============================================================
        # STEP 1: CONSISTENT CHARACTER GENERATION (4 credits)
        # ============================================================
        print("\n" + "=" * 60)
        print("  STEP 1: CONSISTENT CHARACTER — Generate Ray Image (4 credits)")
        print("=" * 60)

        # Click Character in sidebar
        char_pos = sidebar_pos.get("Character")
        if not char_pos:
            # Try partial match
            for key in sidebar_pos:
                if "Character" in key or "Char" in key:
                    char_pos = sidebar_pos[key]
                    break
        if not char_pos:
            print("  Character tool not in sidebar. Available tools:")
            print(f"  {list(sidebar_pos.keys())}")
        else:
            print(f"\n  Clicking Character at {char_pos}...")
            page.mouse.click(*char_pos)
            page.wait_for_timeout(2000)
            close_all_dialogs(page)
            ss(page, "char_panel")
            panel = map_panel(page, "Character Panel")

            # Look for "Generate Images" in panel
            gen_found = False
            for item in panel:
                if "Generate Images" in item["text"]:
                    print(f"\n  Clicking 'Generate Images' at ({item['x']},{item['y']})")
                    page.mouse.click(item["x"] + item["w"]//2, item["y"] + item["h"]//2)
                    page.wait_for_timeout(2000)
                    close_all_dialogs(page)
                    gen_found = True
                    break

            if not gen_found:
                # Try button click
                page.evaluate("""() => {
                    for (const el of document.querySelectorAll('*')) {
                        const text = (el.innerText || '').trim();
                        const rect = el.getBoundingClientRect();
                        if (text === 'Generate Images' && rect.x > 60 && rect.x < 500 && rect.width > 0) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(2000)
                close_all_dialogs(page)

            ss(page, "cc_panel")
            cc_panel = map_panel(page, "Consistent Character")

            # Find textarea for scene description
            textarea = page.evaluate("""() => {
                for (const el of document.querySelectorAll('textarea')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 20) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                placeholder: el.placeholder || '', tag: 'textarea'};
                    }
                }
                for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 20) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, tag: 'contenteditable'};
                    }
                }
                // Look for any input-like element in the panel
                for (const el of document.querySelectorAll('input, [role="textbox"]')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 500 && rect.width > 100) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                tag: el.tagName, type: el.type || ''};
                    }
                }
                return null;
            }""")
            print(f"\n  Textarea: {textarea}")

            if textarea:
                page.mouse.click(textarea["x"] + 50, textarea["y"] + 10)
                page.wait_for_timeout(300)
                page.keyboard.press("Meta+a")
                page.wait_for_timeout(100)

                scene = "Standing behind a modern desk in a minimalist studio, one hand resting on desk, confident smile, looking directly at camera, soft studio lighting, clean white background"
                page.keyboard.type(scene, delay=5)
                page.wait_for_timeout(500)
                ss(page, "cc_typed")
                print(f"  Typed scene ({len(scene)} chars)")
            else:
                # Maybe the textarea is below the fold — scroll the panel
                print("  No textarea found. Trying to scroll panel and find it...")
                # Find the panel container and scroll it
                page.evaluate("""() => {
                    // Find scrollable panel area
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 100 && rect.width > 250 && rect.height > 400 &&
                            el.scrollHeight > el.clientHeight) {
                            el.scrollBy(0, 300);
                            return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(500)

                textarea = page.evaluate("""() => {
                    for (const el of document.querySelectorAll('textarea, [contenteditable="true"]')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 20) {
                            return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, tag: el.tagName};
                        }
                    }
                    return null;
                }""")
                print(f"  Textarea after scroll: {textarea}")

                if textarea:
                    page.mouse.click(textarea["x"] + 50, textarea["y"] + 10)
                    page.wait_for_timeout(300)
                    scene = "Standing in minimalist studio, confident smile, looking at camera, soft lighting"
                    page.keyboard.type(scene, delay=5)
                    page.wait_for_timeout(500)
                    ss(page, "cc_typed")

            # Count results before generating
            initial = count_results(page)
            print(f"\n  Current results: {initial}")

            # Click Generate button (should say "Generate 4" for 4 credits)
            gen_btn = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.x > 60 && rect.x < 500 &&
                        rect.width > 50 && rect.y > 200 && !btn.disabled) {
                        return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                                w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")
            print(f"  Generate button: {gen_btn}")

            if gen_btn:
                page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
                page.wait_for_timeout(1000)
                ss(page, "cc_generating")

                # Check for errors or popups
                page.wait_for_timeout(2000)
                close_all_dialogs(page)

                # Wait for generation
                success = wait_for_generation(page, initial, timeout_s=90, label="cc")
                if success:
                    new_count = count_results(page)
                    print(f"  Total results: {new_count} (was {initial})")
            else:
                print("  No Generate button found")
                ss(page, "cc_no_gen_btn")

        # Close panel for next test
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # ============================================================
        # STEP 2: TXT2IMG GENERATION (20 credits)
        # ============================================================
        print("\n" + "=" * 60)
        print("  STEP 2: TXT2IMG — Generate Ray Image (20 credits)")
        print("=" * 60)

        txt_pos = sidebar_pos.get("Txt2Img")
        if not txt_pos:
            for key in sidebar_pos:
                if "Txt" in key or "txt" in key:
                    txt_pos = sidebar_pos[key]
                    break

        if not txt_pos:
            print("  Txt2Img not in sidebar")
        else:
            print(f"\n  Clicking Txt2Img at {txt_pos}...")
            page.mouse.click(*txt_pos)
            page.wait_for_timeout(2000)
            close_all_dialogs(page)
            ss(page, "txt2img_panel")
            t2i_panel = map_panel(page, "Txt2Img Panel")

            # Find prompt textarea
            prompt_el = page.evaluate("""() => {
                for (const el of document.querySelectorAll('textarea')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 30) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                placeholder: el.placeholder || '', tag: 'textarea'};
                    }
                }
                for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 30) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, tag: 'contenteditable'};
                    }
                }
                return null;
            }""")
            print(f"\n  Prompt element: {prompt_el}")

            if prompt_el:
                page.mouse.click(prompt_el["x"] + 50, prompt_el["y"] + 15)
                page.wait_for_timeout(300)
                page.keyboard.press("Meta+a")
                page.wait_for_timeout(100)

                prompt = "Ray, young adult male YouTuber, light skin, short dark hair, charcoal gray t-shirt. Standing in modern minimalist studio, soft directional lighting, clean white background. Medium shot waist up, natural confident smile, facing camera. Professional portrait, photorealistic, 4K."
                page.keyboard.type(prompt, delay=3)
                page.wait_for_timeout(500)
                ss(page, "txt2img_typed")
                print(f"  Typed prompt ({len(prompt)} chars)")

                initial = count_results(page)

                # Click Generate
                gen_btn = page.evaluate("""() => {
                    for (const btn of document.querySelectorAll('button')) {
                        const text = (btn.innerText || '').trim();
                        const rect = btn.getBoundingClientRect();
                        if (text.includes('Generate') && rect.x > 60 && rect.x < 500 &&
                            rect.width > 50 && rect.y > 200 && !btn.disabled) {
                            return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                                    w: rect.width, h: rect.height};
                        }
                    }
                    return null;
                }""")
                print(f"\n  Generate button: {gen_btn}")

                if gen_btn:
                    page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
                    page.wait_for_timeout(1000)
                    ss(page, "txt2img_generating")

                    page.wait_for_timeout(2000)
                    close_all_dialogs(page)

                    success = wait_for_generation(page, initial, timeout_s=120, label="txt2img")
                    if success:
                        print(f"  Results: {count_results(page)}")

                        # Take screenshot of the generated result
                        ss(page, "txt2img_result")
                else:
                    print("  No Generate button found")
                    ss(page, "txt2img_no_gen")
            else:
                print("  No prompt element found")

        # Close panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # ============================================================
        # STEP 3: PLACE IMAGE ON CANVAS + DOWNLOAD
        # ============================================================
        print("\n" + "=" * 60)
        print("  STEP 3: INTERACT WITH GENERATED RESULTS")
        print("=" * 60)

        # Click on the most recent result to see action buttons
        result_imgs = page.evaluate("""() => {
            const imgs = [];
            for (const img of document.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.x > 1050 && r.y > 80 && r.width > 40 && r.height > 40) {
                    imgs.push({src: img.src.substring(0, 120), x: r.x, y: r.y,
                               w: Math.round(r.width), h: Math.round(r.height)});
                }
            }
            return imgs;
        }""")
        print(f"\n  Result images: {len(result_imgs)}")

        if result_imgs:
            # Click the first (most recent / top) result
            first = result_imgs[0]
            print(f"  Clicking first result at ({first['x']:.0f},{first['y']:.0f})...")
            page.mouse.click(first["x"] + first["w"]//2, first["y"] + first["h"]//2)
            page.wait_for_timeout(1500)
            ss(page, "result_clicked")

            # Check what actions appeared — look for action buttons near the clicked image
            actions = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('button, [role="button"], a, svg')) {
                    const rect = el.getBoundingClientRect();
                    // Look in the results panel area
                    if (rect.x > 1000 && rect.width > 0 && rect.height > 0 && rect.y < 300) {
                        const text = (el.innerText || el.title || el.getAttribute('aria-label') || '').trim();
                        const cls = (el.className || '').toString().substring(0, 30);
                        if (text || el.tagName === 'SVG' || cls) {
                            items.push({text: text.substring(0, 40), tag: el.tagName,
                                       x: Math.round(rect.x), y: Math.round(rect.y),
                                       w: Math.round(rect.width), h: Math.round(rect.height)});
                        }
                    }
                }
                const seen = new Set();
                return items.filter(i => {
                    const key = `${i.x},${i.y},${i.text}`;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).slice(0, 20);
            }""")
            print(f"\n  Action buttons near result:")
            for a in actions:
                print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> '{a['text']}'")

            # Look for "place on canvas" or download buttons
            # From Phase 10, the preview has icon buttons for: favorite, place-on-canvas, download, close
            # They appear on hover over the result image

            # Hover over the result to show action icons
            page.mouse.move(first["x"] + first["w"]//2, first["y"] + first["h"]//2)
            page.wait_for_timeout(1000)

            hover_actions = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    // Look for small action buttons that appeared on hover
                    if (rect.x > 1050 && rect.y > 60 && rect.y < 350 &&
                        rect.width > 10 && rect.width < 60 && rect.height > 10 && rect.height < 60) {
                        const text = (el.title || el.getAttribute('aria-label') || el.innerText || '').trim();
                        const hasSvg = !!el.querySelector('svg');
                        if (text || hasSvg) {
                            items.push({text: text.substring(0, 30), tag: el.tagName,
                                       x: Math.round(rect.x), y: Math.round(rect.y),
                                       w: Math.round(rect.width), h: Math.round(rect.height),
                                       hasSvg});
                        }
                    }
                }
                const seen = new Set();
                return items.filter(i => {
                    const key = `${i.x},${i.y}`;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).slice(0, 10);
            }""")
            print(f"\n  Hover action icons:")
            for a in hover_actions:
                print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> '{a['text']}' svg={a['hasSvg']}")

            ss(page, "result_hover")

            # Try to find and click "Place on canvas" or similar
            placed = page.evaluate("""() => {
                // Look for any button/link with place/canvas/add text or icon
                for (const el of document.querySelectorAll('button, [role="button"], div[class*="action"], div[class*="icon"]')) {
                    const text = (el.title || el.getAttribute('aria-label') || el.innerText || '').trim().toLowerCase();
                    const rect = el.getBoundingClientRect();
                    if ((text.includes('place') || text.includes('canvas') || text.includes('add')) &&
                        rect.x > 1050 && rect.width > 0) {
                        el.click();
                        return {text, x: rect.x, y: rect.y};
                    }
                }
                return null;
            }""")
            print(f"\n  Place on canvas: {placed}")

            if placed:
                page.wait_for_timeout(2000)
                ss(page, "placed_on_canvas")

            # Try double-clicking the result (from Phase 10, this placed image on canvas)
            if not placed:
                print("  Trying double-click to place on canvas...")
                page.mouse.dblclick(first["x"] + first["w"]//2, first["y"] + first["h"]//2)
                page.wait_for_timeout(2000)
                ss(page, "dblclick_result")

        # ============================================================
        # STEP 4: CHECK CANVAS LAYERS
        # ============================================================
        print("\n" + "=" * 60)
        print("  STEP 4: CHECK CANVAS STATE")
        print("=" * 60)

        # Click the Layers tab in the right panel
        layers_btn = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Layers' && rect.x > 1200 && rect.y < 80 && rect.width > 30) {
                    el.click();
                    return {x: rect.x, y: rect.y};
                }
            }
            return null;
        }""")
        print(f"\n  Clicked Layers tab: {layers_btn}")
        page.wait_for_timeout(1000)
        ss(page, "layers_panel")

        # Map layers
        layers = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.x > 1050 && rect.y > 60 && text.includes('Layer') &&
                    text.length < 40 && rect.width > 30) {
                    items.push({text, x: Math.round(rect.x), y: Math.round(rect.y),
                               w: Math.round(rect.width), h: Math.round(rect.height)});
                }
            }
            return items;
        }""")
        print(f"\n  Layers ({len(layers)}):")
        for l in layers:
            print(f"    ({l['x']},{l['y']}) {l['w']}x{l['h']} '{l['text']}'")

        # ============================================================
        # STEP 5: CHAT EDITOR GENERATION (20 credits)
        # ============================================================
        print("\n" + "=" * 60)
        print("  STEP 5: CHAT EDITOR — Generate Ray Image (20 credits)")
        print("=" * 60)

        # Deselect any layer first
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # The chat editor should be at the bottom center
        # From Phase 13 findings: the collapsed bar is around y=850-870
        # Let me look for it by checking all interactive elements near the bottom

        # First, map the entire bottom area
        bottom = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 800 && rect.y < 900 && rect.x > 200 && rect.x < 1100 &&
                    rect.width > 30 && rect.height > 10) {
                    const text = (el.innerText || '').trim();
                    const tag = el.tagName;
                    const cls = (el.className || '').toString().substring(0, 30);
                    const ce = el.contentEditable === 'true';
                    const isTA = tag === 'TEXTAREA';
                    if (text || ce || isTA || cls) {
                        items.push({text: text.substring(0, 60), tag, cls, ce, isTA,
                                   x: Math.round(rect.x), y: Math.round(rect.y),
                                   w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 15);
        }""")
        print(f"\n  Bottom area (y > 800):")
        for item in bottom:
            flags = []
            if item['ce']: flags.append("CE")
            if item['isTA']: flags.append("TA")
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> [{','.join(flags)}] [{item['cls'][:15]}] {item['text'][:40]}")

        # Try clicking the center bottom to activate chat
        print("\n  Clicking center bottom to activate chat...")
        page.mouse.click(600, 860)
        page.wait_for_timeout(1500)

        # Check for expanded chat editor
        chat_input = page.evaluate("""() => {
            // First try contenteditable
            for (const el of document.querySelectorAll('[contenteditable="true"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 500 && rect.width > 100 && rect.height > 10) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'contenteditable'};
                }
            }
            // Then try textarea
            for (const el of document.querySelectorAll('textarea')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 500 && rect.width > 100) {
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height, type: 'textarea'};
                }
            }
            return null;
        }""")
        print(f"  Chat input: {chat_input}")
        ss(page, "chat_area")

        if not chat_input:
            # The chat might need a different click location or it might be collapsed differently
            # Try clicking more precisely in the center chat bar area
            print("  Trying different click locations for chat bar...")

            for y in [870, 850, 880, 840]:
                page.mouse.click(500, y)
                page.wait_for_timeout(800)
                chat_input = page.evaluate("""() => {
                    for (const el of document.querySelectorAll('[contenteditable="true"], textarea')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.y > 500 && rect.width > 100 && rect.height > 10) {
                            return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                    type: el.contentEditable === 'true' ? 'contenteditable' : 'textarea'};
                        }
                    }
                    return null;
                }""")
                if chat_input:
                    print(f"  Found chat input at y={y}!")
                    break

        if chat_input:
            page.mouse.click(chat_input["x"] + 50, chat_input["y"] + chat_input["h"]//2)
            page.wait_for_timeout(300)

            prompt = "Ray, young adult male YouTuber with light skin and short dark hair, wearing charcoal gray t-shirt. Standing in clean modern studio holding a product box in his right hand, showing it to camera with enthusiastic expression. Minimalist white background, soft professional lighting. Medium shot waist up. Photorealistic, 4K quality."
            page.keyboard.type(prompt, delay=3)
            page.wait_for_timeout(500)
            ss(page, "chat_typed")
            print(f"  Typed prompt ({len(prompt)} chars)")

            initial = count_results(page)

            # Click Generate
            gen_btn = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.y > 500 && !btn.disabled &&
                        rect.width > 30) {
                        return {text: text.substring(0, 40), x: rect.x, y: rect.y,
                                w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")
            print(f"\n  Generate button: {gen_btn}")

            if gen_btn:
                page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
                page.wait_for_timeout(1000)
                ss(page, "chat_generating")

                page.wait_for_timeout(2000)
                close_all_dialogs(page)

                success = wait_for_generation(page, initial, timeout_s=120, label="chat")
                if success:
                    print(f"  Results: {count_results(page)}")
                    ss(page, "chat_result")
        else:
            print("  Chat editor not found. Will map all visible elements at bottom...")
            # Map everything visible in lower half
            all_bottom = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.y > 700 && rect.y < 900 && rect.width > 20 && rect.height > 10 &&
                        el.children.length < 3) {
                        const text = (el.innerText || '').trim();
                        if (text && text.length > 0 && text.length < 60) {
                            items.push({text, tag: el.tagName,
                                       x: Math.round(rect.x), y: Math.round(rect.y),
                                       w: Math.round(rect.width), h: Math.round(rect.height),
                                       cls: (el.className || '').toString().substring(0, 20)});
                        }
                    }
                }
                const seen = new Set();
                return items.filter(i => {
                    if (seen.has(i.text)) return false;
                    seen.add(i.text);
                    return true;
                }).sort((a, b) => a.y - b.y).slice(0, 20);
            }""")
            print(f"  All visible elements (y > 700):")
            for item in all_bottom:
                print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> [{item['cls'][:15]}] '{item['text']}'")
            ss(page, "chat_debug")

        # ============================================================
        # FINAL: Credit balance
        # ============================================================
        print("\n" + "=" * 60)
        print("  FINAL: CREDIT BALANCE + SUMMARY")
        print("=" * 60)

        # Credits info from top bar
        credits = page.evaluate("""() => {
            const info = {};
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.y < 30 && rect.width > 0) {
                    if (text === 'Unlimited' || /^\d[\d,]*$/.test(text)) {
                        info[`val_${Math.round(rect.x)}`] = text;
                    }
                    if (text.includes('credit') || text.includes('Credit')) {
                        info.label = text;
                    }
                }
            }
            return info;
        }""")
        print(f"\n  Credits: {credits}")

        total_results = count_results(page)
        print(f"  Total results in project: {total_results}")
        ss(page, "final")

        print("\n\n===== PHASE 15 COMPLETE =====")

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
