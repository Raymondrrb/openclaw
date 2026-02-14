"""Phase 11: Generate Ray via Consistent Character + place on canvas + explore tools.

Fix: Don't Escape after clicking sidebar. Properly open Character submenu.
Credits: user authorized spending yellow credits freely.
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
    path = OUT_DIR / f"E{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: E{_N:02d}_{name}")


def close_popup(page):
    try:
        btn = page.locator('button:has-text("Not now")')
        if btn.count() > 0 and btn.first.is_visible(timeout=1500):
            btn.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


def click_in_sidebar(page, tool_name):
    """Click a sidebar tool. Does NOT close panels first."""
    clicked = page.evaluate("""(name) => {
        for (const el of document.querySelectorAll('*')) {
            const rect = el.getBoundingClientRect();
            const text = (el.innerText || '').trim().replace(/\\n/g, ' ');
            if (rect.x >= 0 && rect.x < 65 && rect.width > 10 && rect.width < 70 &&
                rect.height > 10 && rect.y > 50) {
                if (text === name || text.startsWith(name)) {
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


def click_in_panel(page, text_starts_with):
    """Click a visible element in the left panel area (x: 60-400)."""
    return page.evaluate("""(prefix) => {
        for (const el of document.querySelectorAll('*')) {
            const rect = el.getBoundingClientRect();
            if (rect.x > 60 && rect.x < 400 && rect.width > 30 && rect.height > 10 &&
                rect.y > 50 && rect.y < 900) {
                const text = (el.innerText || '').trim();
                if (text.startsWith(prefix) && el.children.length < 5) {
                    el.click();
                    return {text: text.substring(0, 60), y: rect.y};
                }
            }
        }
        return null;
    }""", text_starts_with)


def count_result_imgs(page):
    """Count result images in the right panel."""
    return page.evaluate("""() => {
        let count = 0;
        for (const img of document.querySelectorAll('img')) {
            const rect = img.getBoundingClientRect();
            if (rect.x > 1050 && rect.y > 80 && rect.width > 50 && rect.height > 50) count++;
        }
        return count;
    }""")


def wait_generation(page, initial, max_s=150):
    """Wait for new results to appear."""
    start = time.monotonic()
    while time.monotonic() - start < max_s:
        page.wait_for_timeout(5000)
        cur = count_result_imgs(page)
        elapsed = time.monotonic() - start
        if cur > initial:
            print(f"  Done! {cur} results (was {initial}) in {elapsed:.0f}s")
            return True
        print(f"  ... {elapsed:.0f}s (results: {cur})")
    print(f"  Timeout after {max_s}s")
    return False


def map_panel(page, label=""):
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
        # ===================================================================
        # PART A: Place existing result on canvas (from right panel)
        # ===================================================================
        print("\n" + "="*60)
        print("PART A: Place existing Ray image on canvas")
        print("="*60)

        # The right panel already has Character Sheet results from before.
        # Double-click a result image to place it on canvas.
        placed = page.evaluate("""() => {
            const imgs = [];
            for (const img of document.querySelectorAll('img')) {
                const rect = img.getBoundingClientRect();
                // Right panel, first result set (y < 300)
                if (rect.x > 1050 && rect.y > 100 && rect.y < 300 && rect.width > 50) {
                    imgs.push({src: (img.src || '').substring(0, 80), x: rect.x, y: rect.y,
                               w: rect.width, h: rect.height});
                }
            }
            return imgs;
        }""")
        print(f"  Result images in first set: {len(placed)}")
        for p in placed:
            print(f"    ({p['x']:.0f},{p['y']:.0f}) {p['w']:.0f}x{p['h']:.0f}")

        if placed:
            # Click the first image
            x, y = placed[0]['x'] + placed[0]['w']/2, placed[0]['y'] + placed[0]['h']/2
            print(f"\n  Clicking result image at ({x:.0f}, {y:.0f})...")
            page.mouse.click(x, y)
            page.wait_for_timeout(3000)
            ss(page, "after_click_result")

            # Check if a preview opened or if image was placed
            preview = page.locator('#result-preview')
            if preview.count() > 0 and preview.first.is_visible(timeout=1000):
                print("  Result preview opened")
                ss(page, "result_preview")

                # Look for a "Place on canvas" or similar button
                preview_actions = page.evaluate("""() => {
                    const items = [];
                    const preview = document.querySelector('#result-preview');
                    if (!preview) return items;
                    for (const el of preview.querySelectorAll('button, [role="button"], [class*="action"], [class*="btn"]')) {
                        const text = (el.innerText || '').trim();
                        const title = el.getAttribute('title') || '';
                        const cls = (el.className || '').toString().substring(0, 40);
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0) {
                            items.push({text: text.substring(0, 40), title, cls, x: rect.x, y: rect.y});
                        }
                    }
                    return items;
                }""")
                print(f"  Preview actions:")
                for a in preview_actions:
                    ident = a['title'] or a['text'] or a['cls'][:25]
                    print(f"    ({a['x']:.0f},{a['y']:.0f}) {ident}")

                # Close preview
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

        # Try double-clicking to place on canvas
        if placed:
            x, y = placed[0]['x'] + placed[0]['w']/2, placed[0]['y'] + placed[0]['h']/2
            print(f"\n  Double-clicking result image at ({x:.0f}, {y:.0f})...")
            page.mouse.dblclick(x, y)
            page.wait_for_timeout(3000)
            ss(page, "after_dblclick")

            # Check layers
            layer_check = page.evaluate("""() => {
                const layers = document.querySelectorAll('[class*="layer-item"], [class*="layer-row"]');
                const items = [];
                for (const l of layers) {
                    items.push((l.innerText || '').trim().substring(0, 40));
                }
                return {count: layers.length, items};
            }""")
            print(f"  Layers after dblclick: {layer_check}")

        # If still no layer, try dragging from right panel to canvas
        canvas_has_layer = page.evaluate("""() => {
            // Check if canvas area has any images (besides the upload placeholder)
            const canvas = document.querySelector('#canvas');
            if (!canvas) return false;
            const imgs = canvas.querySelectorAll('img');
            return imgs.length > 0;
        }""")
        print(f"  Canvas has images: {canvas_has_layer}")

        if not canvas_has_layer:
            # Alternative: use the "Chat Editor" action button on a result
            print("\n  Trying 'Chat Editor' action button on result...")
            ce_action = page.evaluate("""() => {
                for (const el of document.querySelectorAll('[class*="gen-handle-func"]')) {
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    if (rect.x > 1050 && rect.y > 300 && rect.y < 400 && text.includes('Chat Editor')) {
                        return {x: rect.x + rect.width/2, y: rect.y + rect.height/2, text};
                    }
                }
                return null;
            }""")
            if ce_action:
                print(f"  Clicking '{ce_action['text']}' at ({ce_action['x']:.0f}, {ce_action['y']:.0f})")
                page.mouse.click(ce_action['x'], ce_action['y'])
                page.wait_for_timeout(3000)
                ss(page, "chat_editor_action")

        # ===================================================================
        # PART B: Generate via Consistent Character
        # ===================================================================
        print("\n" + "="*60)
        print("PART B: Generate Ray via Consistent Character (4 credits)")
        print("="*60)

        # Step 1: Click Character in sidebar
        print("  Step 1: Click Character sidebar")
        click_in_sidebar(page, "Character")
        page.wait_for_timeout(2000)
        ss(page, "character_menu")

        # Step 2: Check what's in the left panel now
        panel_check = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 350 && rect.y > 50 && rect.y < 600 &&
                    rect.width > 30 && rect.height > 15) {
                    const text = (el.innerText || '').trim();
                    if (text && text.length > 2 && text.length < 80 && el.children.length < 5) {
                        items.push({text: text.substring(0, 60), y: Math.round(rect.y),
                                   tag: el.tagName, cls: (el.className || '').toString().substring(0, 30)});
                    }
                }
            }
            // Deduplicate
            const seen = new Set();
            return items.filter(i => { const k = i.text; if (seen.has(k)) return false; seen.add(k); return true; })
                       .sort((a, b) => a.y - b.y).slice(0, 20);
        }""")
        print(f"  Panel items after Character click:")
        for item in panel_check:
            print(f"    y={item['y']} <{item['tag']}> [{item['cls']}] {item['text']}")

        # Step 3: Click "Generate Images" from the submenu
        gen_imgs = click_in_panel(page, "Generate Images")
        if gen_imgs:
            print(f"\n  Clicked: {gen_imgs}")
            page.wait_for_timeout(3000)
            ss(page, "consistent_char_opened")

            # Verify Consistent Character panel is open
            cc_check = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 300 && rect.y > 50 && rect.y < 100) {
                        const text = (el.innerText || '').trim();
                        if (text.includes('Consistent Character')) return true;
                    }
                }
                return false;
            }""")
            print(f"  Consistent Character panel open: {cc_check}")

            if cc_check:
                # Map the full panel
                map_panel(page, "Consistent Character")

                # Step 4: Set action/scene prompt
                scene = "Ray standing in a modern, minimalist studio with soft neutral lighting. Looking directly at camera with a calm, confident expression. Medium shot from waist up, arms relaxed at sides. Clean white-gray background. Professional YouTube presenter pose. Photorealistic. Suitable for AI lipsync talking head."

                set_scene = page.evaluate("""(text) => {
                    // Find the second textarea (Character Action & Scene)
                    const textareas = document.querySelectorAll('textarea');
                    for (const ta of textareas) {
                        const rect = ta.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.y > 280) {
                            // Clear and set new value
                            ta.focus();
                            ta.select();
                            return {found: true, y: rect.y, oldLen: ta.value.length};
                        }
                    }
                    return {found: false};
                }""", scene)
                print(f"\n  Scene textarea: {set_scene}")

                if set_scene.get("found"):
                    # Type the new scene (clear first with Ctrl+A then type)
                    page.keyboard.press("Control+a")
                    page.wait_for_timeout(200)
                    page.keyboard.type(scene, delay=5)
                    page.wait_for_timeout(1000)
                    ss(page, "scene_typed")

                # Step 5: Set aspect ratio to 16:9 for YouTube
                page.evaluate("""() => {
                    for (const el of document.querySelectorAll('div, button')) {
                        const rect = el.getBoundingClientRect();
                        const text = (el.innerText || '').trim();
                        if (text === '16:9' && rect.x > 60 && rect.x < 400 && rect.y > 600) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(500)

                # Step 6: Set Normal mode (good quality, 4 credits)
                page.evaluate("""() => {
                    for (const btn of document.querySelectorAll('button')) {
                        const text = (btn.innerText || '').trim();
                        const rect = btn.getBoundingClientRect();
                        if (text === 'Normal' && rect.x > 60 && rect.x < 400) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(500)

                # Step 7: Count initial results
                initial = count_result_imgs(page)
                print(f"\n  Initial results: {initial}")

                # Step 8: Scroll down to find Generate button and click it
                ss(page, "before_generate")

                # Scroll the panel down first
                page.evaluate("""() => {
                    const panel = document.querySelector('.gen-config-form') ||
                                  document.querySelector('.gen-config-body') ||
                                  document.querySelector('[class*="gen-config"]');
                    if (panel) {
                        panel.scrollTop = panel.scrollHeight;
                    }
                }""")
                page.wait_for_timeout(500)

                gen_btn = page.evaluate("""() => {
                    for (const btn of document.querySelectorAll('button')) {
                        const text = (btn.innerText || '').trim();
                        const rect = btn.getBoundingClientRect();
                        const cls = (btn.className || '').toString();
                        if (text.startsWith('Generate') && rect.x > 60 && rect.x < 400 &&
                            rect.width > 100 && !btn.disabled) {
                            btn.click();
                            return {text, x: rect.x, y: rect.y, cls: cls.substring(0, 40)};
                        }
                    }
                    return null;
                }""")
                print(f"\n  Generate button: {gen_btn}")

                if gen_btn:
                    ss(page, "generating")
                    print("  Waiting for generation...")

                    if wait_generation(page, initial, max_s=150):
                        ss(page, "generation_complete")

                        # Click the new result to place on canvas
                        page.wait_for_timeout(2000)

                        # Check if "Generation Complete!" dialog appeared
                        gen_dialog = page.evaluate("""() => {
                            for (const el of document.querySelectorAll('*')) {
                                const text = (el.innerText || '').trim();
                                if (text.includes('Generation Complete')) {
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        print(f"  Generation Complete dialog: {gen_dialog}")
                        ss(page, "gen_dialog_check")

                        # Try to find and click the result to add to canvas
                        # The newest result should be at the top of the results panel
                        new_result = page.evaluate("""() => {
                            const imgs = [];
                            for (const img of document.querySelectorAll('img')) {
                                const rect = img.getBoundingClientRect();
                                if (rect.x > 1050 && rect.y > 80 && rect.y < 400 &&
                                    rect.width > 40 && rect.height > 40) {
                                    imgs.push({x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                               src: (img.src || '').substring(0, 80)});
                                }
                            }
                            return imgs.sort((a, b) => a.y - b.y);
                        }""")
                        print(f"  Top result images: {len(new_result)}")
                        for r in new_result[:3]:
                            print(f"    ({r['x']:.0f},{r['y']:.0f}) {r['w']:.0f}x{r['h']:.0f}")

                        if new_result:
                            # Double-click first result to place on canvas
                            r = new_result[0]
                            cx, cy = r['x'] + r['w']/2, r['y'] + r['h']/2
                            print(f"\n  Double-clicking result at ({cx:.0f}, {cy:.0f})")
                            page.mouse.dblclick(cx, cy)
                            page.wait_for_timeout(3000)
                            ss(page, "placed_on_canvas")
                else:
                    print("  Generate button not found or disabled!")
                    # Try the generate button by ID
                    page.evaluate("""() => {
                        const btn = document.querySelector('#txt2img-generate-btn');
                        if (btn && !btn.disabled) { btn.click(); return true; }
                        return false;
                    }""")
        else:
            print("  'Generate Images' submenu item not found")
            # Maybe the Character panel didn't open properly
            # Try clicking the sidebar icon again
            print("  Retrying Character click...")
            page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x < 65 && rect.y > 270 && rect.y < 320 && rect.width > 20) {
                        const text = (el.innerText || '').trim();
                        if (text.includes('Character')) {
                            el.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(3000)
            ss(page, "character_retry")
            map_panel(page, "Character retry")

        # ===================================================================
        # PART C: Check canvas state and explore tools
        # ===================================================================
        print("\n" + "="*60)
        print("PART C: Check canvas and explore layer-dependent tools")
        print("="*60)

        # First check if we have layers now
        has_layer = page.evaluate("""() => {
            // Check for the disable-mask — if it's visible, no layer is selected
            for (const el of document.querySelectorAll('.disable-mask')) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return false;
            }
            return true;
        }""")
        print(f"  Has selectable layer: {has_layer}")

        # Check layers panel
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Layers' && el.getBoundingClientRect().x > 1050) {
                    el.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(1000)

        layers_info = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('[class*="layer"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 1050 && rect.y > 80 && rect.width > 50) {
                    const text = (el.innerText || '').trim();
                    if (text && text.length < 60) items.push(text);
                }
            }
            return [...new Set(items)].slice(0, 10);
        }""")
        print(f"  Layers: {layers_info}")
        ss(page, "layers_check")

        # If we still don't have a layer, try uploading/generating via chat
        if not has_layer:
            print("\n  No layer yet — generating via Chat Editor (20 credits)...")

            # Close any open panel
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

            # Click the chat bar to expand it
            page.evaluate("""() => {
                const bar = document.querySelector('[class*="chat-editor-bar"]');
                if (bar) bar.click();
            }""")
            page.wait_for_timeout(1000)

            # Find the contenteditable prompt and type
            prompt_el = page.locator('[contenteditable="true"].custom-textarea')
            if prompt_el.count() > 0:
                try:
                    prompt_el.first.click(force=True, timeout=3000)
                    page.wait_for_timeout(500)

                    prompt_text = "Professional photo of a young adult male YouTuber named Ray, light skin, short dark hair, wearing a charcoal gray t-shirt. Standing in a modern minimalist studio with soft lighting. Medium shot, waist up, looking at camera with confident smile. Clean white background. Photorealistic, 4K quality."

                    page.keyboard.type(prompt_text, delay=10)
                    page.wait_for_timeout(1000)
                    ss(page, "chat_prompt_typed")

                    # Click Generate
                    initial = count_result_imgs(page)
                    gen = page.locator('#chat-editor-generate-btn')
                    if gen.count() > 0:
                        gen.first.click(force=True, timeout=5000)
                        print("  Clicked Chat Generate (20 credits)")
                        ss(page, "chat_generating")

                        if wait_generation(page, initial, max_s=120):
                            ss(page, "chat_gen_done")

                            # Place result on canvas
                            page.wait_for_timeout(2000)
                            new_result = page.evaluate("""() => {
                                const imgs = [];
                                for (const img of document.querySelectorAll('img')) {
                                    const rect = img.getBoundingClientRect();
                                    if (rect.x > 1050 && rect.y > 80 && rect.y < 300 &&
                                        rect.width > 40) {
                                        imgs.push({x: rect.x + rect.width/2, y: rect.y + rect.height/2});
                                    }
                                }
                                return imgs.sort((a, b) => a.y - b.y);
                            }""")
                            if new_result:
                                page.mouse.dblclick(new_result[0]['x'], new_result[0]['y'])
                                page.wait_for_timeout(3000)
                                ss(page, "chat_result_placed")
                    else:
                        print("  Chat Generate button not found")
                except Exception as exc:
                    print(f"  Chat editor error: {exc}")

        # Now try clicking a layer on the canvas
        print("\n  Trying to select a layer on canvas...")
        # Click somewhere in the center of the canvas
        page.mouse.click(700, 450)
        page.wait_for_timeout(1000)

        has_layer2 = page.evaluate("""() => {
            const mask = document.querySelector('.disable-mask');
            if (mask) {
                const rect = mask.getBoundingClientRect();
                return rect.width === 0 || rect.height === 0 ||
                       getComputedStyle(mask).display === 'none';
            }
            return true;
        }""")
        print(f"  Layer selected after click: {has_layer2}")

        if has_layer2:
            print("\n  Layer available! Now exploring tools...")

            # Explore each tool
            for tool_name in ["Txt2Img", "Img2Img", "AI Video", "Lip Sync",
                              "Video Editor", "Motion Control"]:
                print(f"\n--- {tool_name} ---")
                click_in_sidebar(page, tool_name)
                page.wait_for_timeout(1500)
                ss(page, tool_name.replace(" ", "_").lower())
                map_panel(page, tool_name)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

            # Lower sidebar tools
            page.evaluate("""() => {
                const sidebar = document.querySelector('[class*="tool-list"]');
                if (sidebar) sidebar.scrollTop = sidebar.scrollHeight;
            }""")
            page.wait_for_timeout(300)

            for tool_name in ["Enhance", "Image Editor", "Instant"]:
                print(f"\n--- {tool_name} ---")
                click_in_sidebar(page, tool_name)
                page.wait_for_timeout(1500)
                ss(page, tool_name.replace(" ", "_").lower())
                map_panel(page, tool_name)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

            # Top processing tools
            for tool_name in ["AI Eraser", "Hand Repair", "Expression", "BG Remove"]:
                print(f"\n--- {tool_name} ---")
                page.evaluate("""(name) => {
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if ((el.innerText||'').trim() === name && rect.y > 70 && rect.y < 120 && rect.x > 350) {
                            el.click();
                            return;
                        }
                    }
                }""", tool_name)
                page.wait_for_timeout(1500)
                ss(page, tool_name.replace(" ", "_").lower())
                map_panel(page, tool_name)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

        print("\n\n" + "="*60)
        print("PHASE 11 COMPLETE")
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
