"""Phase 12: Debug sidebar clicks + explore tool panels properly.

The canvas has Layer 1 (Ray's Character Sheet image). The sidebar tools
are not opening their left panels. This script investigates why and fixes it.

Hypothesis: need to click the PARENT tool container, not just the text label.
Or: some tools need the layer deselected first.
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
    path = OUT_DIR / f"F{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: F{_N:02d}_{name}")


def close_popup(page):
    try:
        btn = page.locator('button:has-text("Not now")')
        if btn.count() > 0 and btn.first.is_visible(timeout=1500):
            btn.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


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
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("https://www.dzine.ai/canvas?id=19797967",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

    page.bring_to_front()
    page.wait_for_timeout(2000)
    close_popup(page)

    try:
        # ===== STEP 0: Map the sidebar structure =====
        print("\n===== SIDEBAR STRUCTURE =====")

        sidebar_items = page.evaluate("""() => {
            const items = [];
            // Map all elements in the leftmost sidebar area
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.x >= 0 && rect.x < 70 && rect.y > 30 && rect.width > 10 &&
                    rect.width < 80 && rect.height > 30) {
                    const text = (el.innerText || '').trim().replace(/\\n/g, ' ');
                    const tag = el.tagName;
                    const cls = (el.className || '').toString().substring(0, 50);
                    const role = el.getAttribute('role') || '';
                    const onClick = el.onclick ? 'has onclick' : '';
                    if (text && text.length > 2 && text.length < 40) {
                        items.push({text, tag, cls, role, onClick,
                                   x: Math.round(rect.x), y: Math.round(rect.y),
                                   w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
            }
            // Deduplicate by text
            const seen = new Set();
            return items.filter(i => {
                if (seen.has(i.text)) return false;
                seen.add(i.text);
                return true;
            }).sort((a, b) => a.y - b.y);
        }""")

        print(f"\nSidebar items ({len(sidebar_items)}):")
        for item in sidebar_items:
            print(f"  ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> [{item['cls'][:30]}] {item['text']}")

        # ===== STEP 1: Try clicking sidebar items via their parent container =====
        print("\n===== CLICKING VIA PARENT CONTAINER =====")

        # Click Txt2Img properly
        txt2img_info = page.evaluate("""() => {
            // Find the Txt2Img text element and get its clickable parent
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Txt2Img') {
                    const rect = el.getBoundingClientRect();
                    if (rect.x < 70 && rect.y > 50) {
                        // Walk up the DOM to find the clickable parent
                        let parent = el;
                        for (let i = 0; i < 5; i++) {
                            parent = parent.parentElement;
                            if (!parent) break;
                            const pr = parent.getBoundingClientRect();
                            const pcls = (parent.className || '').toString();
                            // Look for a parent that's a tool button container
                            if (pr.width > 20 && pr.height > 30 && (
                                pcls.includes('tool') || pcls.includes('item') ||
                                pcls.includes('tab') || pcls.includes('menu') ||
                                parent.tagName === 'BUTTON' || parent.tagName === 'A')) {
                                return {
                                    found: true,
                                    parentTag: parent.tagName,
                                    parentCls: pcls.substring(0, 60),
                                    parentX: pr.x, parentY: pr.y,
                                    parentW: pr.width, parentH: pr.height,
                                    textX: rect.x, textY: rect.y,
                                };
                            }
                        }
                        // No suitable parent found, return the element itself
                        return {found: true, parentTag: el.tagName,
                                parentCls: (el.className || '').toString().substring(0, 60),
                                parentX: rect.x, parentY: rect.y,
                                parentW: rect.width, parentH: rect.height,
                                textX: rect.x, textY: rect.y};
                    }
                }
            }
            return {found: false};
        }""")
        print(f"\n  Txt2Img element info: {json.dumps(txt2img_info, indent=2)}")

        # ===== STEP 2: Deselect canvas layer and try =====
        print("\n===== DESELECT LAYER FIRST =====")

        # Click empty area on canvas to deselect
        # The transparent checkerboard area should be at the edges
        page.mouse.click(400, 50)  # Top area above canvas
        page.wait_for_timeout(1000)

        # Check if layer is still selected
        selected = page.evaluate("""() => {
            // Look for selection handles on canvas
            const handles = document.querySelectorAll('[class*="handle"], [class*="select-box"], [class*="transformer"]');
            let visible = 0;
            for (const h of handles) {
                const rect = h.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) visible++;
            }
            return {handleCount: visible};
        }""")
        print(f"  Selection handles after click: {selected}")

        # ===== STEP 3: Click Txt2Img using Playwright locator =====
        print("\n===== CLICK Txt2Img WITH PLAYWRIGHT =====")

        # Try clicking the Txt2Img icon (not text) — it's an SVG/icon above the text
        txt2img_clicked = page.evaluate("""() => {
            // Find Txt2Img and click its parent container
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Txt2Img' && el.getBoundingClientRect().x < 70) {
                    // Walk up to find clickable ancestor
                    let target = el.parentElement || el;
                    for (let i = 0; i < 3; i++) {
                        if (target.parentElement) target = target.parentElement;
                    }
                    // Click the found ancestor
                    target.click();
                    return {clicked: true, targetTag: target.tagName,
                            targetCls: (target.className || '').toString().substring(0, 50),
                            targetRect: {x: target.getBoundingClientRect().x,
                                        y: target.getBoundingClientRect().y,
                                        w: target.getBoundingClientRect().width,
                                        h: target.getBoundingClientRect().height}};
                }
            }
            return {clicked: false};
        }""")
        print(f"  Click result: {json.dumps(txt2img_clicked, indent=2)}")
        page.wait_for_timeout(2000)
        ss(page, "txt2img_via_parent")

        # Check what opened
        left_panel = page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                    rect.width > 15 && rect.height > 5) {
                    const text = (el.innerText || '').trim();
                    if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                        seen.add(text);
                        items.push({text: text.substring(0, 80), y: Math.round(rect.y)});
                    }
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 20);
        }""")
        print(f"\n  Left panel after click ({len(left_panel)} items):")
        for item in left_panel:
            print(f"    y={item['y']}: {item['text']}")

        # ===== STEP 4: Try mouse.click at known sidebar position =====
        print("\n===== CLICK AT SIDEBAR POSITION =====")

        # From the sidebar structure, find Txt2Img Y position and click center of its icon
        for item in sidebar_items:
            if 'Txt2Img' in item['text']:
                cx = item['x'] + item['w'] / 2
                cy = item['y'] + item['h'] / 2
                print(f"  Clicking Txt2Img at ({cx:.0f}, {cy:.0f})")
                page.mouse.click(cx, cy)
                page.wait_for_timeout(2000)
                ss(page, "txt2img_mouse_click")

                # Check left panel again
                left2 = page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                            rect.width > 15 && rect.height > 5) {
                            const text = (el.innerText || '').trim();
                            if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                                seen.add(text);
                                items.push({text: text.substring(0, 80), y: Math.round(rect.y)});
                            }
                        }
                    }
                    return items.sort((a, b) => a.y - b.y).slice(0, 20);
                }""")
                print(f"\n  Left panel ({len(left2)} items):")
                for item2 in left2:
                    print(f"    y={item2['y']}: {item2['text']}")
                break

        # ===== STEP 5: Try clicking Img2Img similarly =====
        print("\n===== CLICK Img2Img =====")

        for item in sidebar_items:
            if 'Img2Img' in item['text']:
                cx = item['x'] + item['w'] / 2
                cy = item['y'] + item['h'] / 2
                print(f"  Clicking Img2Img at ({cx:.0f}, {cy:.0f})")
                page.mouse.click(cx, cy)
                page.wait_for_timeout(2000)
                ss(page, "img2img_mouse_click")

                left3 = page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                            rect.width > 15 && rect.height > 5) {
                            const text = (el.innerText || '').trim();
                            if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                                seen.add(text);
                                items.push({text: text.substring(0, 80), y: Math.round(rect.y)});
                            }
                        }
                    }
                    return items.sort((a, b) => a.y - b.y).slice(0, 20);
                }""")
                print(f"\n  Left panel ({len(left3)} items):")
                for item3 in left3:
                    print(f"    y={item3['y']}: {item3['text']}")
                break

        # ===== STEP 6: Check if the layer needs to be CLICKED (selected) first =====
        print("\n===== SELECT LAYER ON CANVAS FIRST =====")

        # Click on the image in the canvas center to select it
        page.mouse.click(400, 300)
        page.wait_for_timeout(1000)
        print("  Clicked canvas center")

        # Now click Img2Img
        for item in sidebar_items:
            if 'Img2Img' in item['text']:
                cx = item['x'] + item['w'] / 2
                cy = item['y'] + item['h'] / 2
                page.mouse.click(cx, cy)
                page.wait_for_timeout(2000)
                ss(page, "img2img_after_select")

                left4 = page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                            rect.width > 15 && rect.height > 5) {
                            const text = (el.innerText || '').trim();
                            if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                                seen.add(text);
                                items.push({text: text.substring(0, 80), y: Math.round(rect.y)});
                            }
                        }
                    }
                    return items.sort((a, b) => a.y - b.y).slice(0, 30);
                }""")
                print(f"\n  Left panel with selected layer ({len(left4)} items):")
                for item4 in left4:
                    print(f"    y={item4['y']}: {item4['text']}")
                break

        # ===== STEP 7: Try Character sidebar with layer selected =====
        print("\n===== CHARACTER WITH LAYER SELECTED =====")

        # First select the layer
        page.mouse.click(400, 300)
        page.wait_for_timeout(500)

        for item in sidebar_items:
            if item['text'] == 'Character':
                cx = item['x'] + item['w'] / 2
                cy = item['y'] + item['h'] / 2
                page.mouse.click(cx, cy)
                page.wait_for_timeout(2000)
                ss(page, "character_with_layer")

                left5 = page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                            rect.width > 15 && rect.height > 5) {
                            const text = (el.innerText || '').trim();
                            if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                                seen.add(text);
                                items.push({text: text.substring(0, 80), y: Math.round(rect.y)});
                            }
                        }
                    }
                    return items.sort((a, b) => a.y - b.y).slice(0, 30);
                }""")
                print(f"\n  Character panel ({len(left5)} items):")
                for item5 in left5:
                    print(f"    y={item5['y']}: {item5['text']}")
                break

        # ===== STEP 8: Try Lip Sync =====
        print("\n===== LIP SYNC WITH LAYER =====")

        page.mouse.click(400, 300)
        page.wait_for_timeout(500)

        for item in sidebar_items:
            if 'Lip Sync' in item['text']:
                cx = item['x'] + item['w'] / 2
                cy = item['y'] + item['h'] / 2
                page.mouse.click(cx, cy)
                page.wait_for_timeout(2000)
                ss(page, "lip_sync_with_layer")

                left6 = page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                            rect.width > 15 && rect.height > 5) {
                            const text = (el.innerText || '').trim();
                            if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                                seen.add(text);
                                items.push({text: text.substring(0, 80), y: Math.round(rect.y)});
                            }
                        }
                    }
                    return items.sort((a, b) => a.y - b.y).slice(0, 30);
                }""")
                print(f"\n  Lip Sync panel ({len(left6)} items):")
                for item6 in left6:
                    print(f"    y={item6['y']}: {item6['text']}")
                break

        # ===== STEP 9: Generate via Chat Editor (20 credits) =====
        print("\n===== GENERATE VIA CHAT EDITOR =====")

        # Deselect layer first
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # Click the chat bar to open it
        chat_bar = page.evaluate("""() => {
            for (const el of document.querySelectorAll('[class*="chat-editor"]')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 700 && rect.width > 200 && rect.height > 30) {
                    el.click();
                    return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                }
            }
            return null;
        }""")
        print(f"  Chat bar: {chat_bar}")
        page.wait_for_timeout(1500)
        ss(page, "chat_bar_clicked")

        # Now check if prompt is visible
        prompt_visible = page.evaluate("""() => {
            const ce = document.querySelector('[contenteditable="true"].custom-textarea');
            if (!ce) return {found: false};
            const rect = ce.getBoundingClientRect();
            return {found: true, x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                    visible: rect.width > 0 && rect.height > 0};
        }""")
        print(f"  Prompt: {prompt_visible}")

        if prompt_visible.get('visible'):
            # Type a prompt
            prompt_text = "Professional headshot of Ray, young adult male, light skin, short dark hair, charcoal gray t-shirt, confident warm smile, modern studio, soft lighting, clean white background, photorealistic 4K, waist up, facing camera"

            # Click the prompt area
            page.mouse.click(prompt_visible['x'] + 100, prompt_visible['y'] + 10)
            page.wait_for_timeout(500)
            page.keyboard.type(prompt_text, delay=10)
            page.wait_for_timeout(1000)
            ss(page, "prompt_typed")

            # Count current results
            initial = page.evaluate("""() => {
                let c = 0;
                for (const img of document.querySelectorAll('img')) {
                    const r = img.getBoundingClientRect();
                    if (r.x > 1050 && r.y > 80 && r.width > 40) c++;
                }
                return c;
            }""")
            print(f"  Initial results: {initial}")

            # Click Generate
            gen = page.evaluate("""() => {
                const btn = document.querySelector('#chat-editor-generate-btn');
                if (btn) {
                    const rect = btn.getBoundingClientRect();
                    return {found: true, disabled: btn.disabled, x: rect.x, y: rect.y,
                            text: (btn.innerText || '').trim()};
                }
                return {found: false};
            }""")
            print(f"  Generate button: {gen}")

            if gen.get('found') and not gen.get('disabled'):
                page.mouse.click(gen['x'] + 50, gen['y'] + 15)
                print("  Clicked Generate! (20 credits)")
                page.wait_for_timeout(3000)
                ss(page, "generating")

                # Wait for result
                start = time.monotonic()
                while time.monotonic() - start < 120:
                    page.wait_for_timeout(5000)
                    cur = page.evaluate("""() => {
                        let c = 0;
                        for (const img of document.querySelectorAll('img')) {
                            const r = img.getBoundingClientRect();
                            if (r.x > 1050 && r.y > 80 && r.width > 40) c++;
                        }
                        return c;
                    }""")
                    elapsed = time.monotonic() - start
                    if cur > initial:
                        print(f"  Generation done! {cur} results in {elapsed:.0f}s")
                        ss(page, "gen_done")
                        break
                    print(f"  ... {elapsed:.0f}s (results: {cur})")
            else:
                print("  Generate disabled or not found")
                # Try clicking the Generate button area directly
                page.mouse.click(950, 790)
                page.wait_for_timeout(2000)
                ss(page, "gen_click_direct")

        print("\n\n===== PHASE 12 COMPLETE =====")

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
