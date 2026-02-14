"""Phase 16: Generate images on Dzine canvas — CC, Txt2Img, Chat Editor.

Browser was restarted with --remote-allow-origins=*. Need to navigate to canvas first.
Credits: Unlimited + 9,000 video.
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
    path = OUT_DIR / f"J{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: J{_N:02d}_{name}")


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


def count_results(page):
    """Count images in the right results panel."""
    return page.evaluate("""() => {
        let c = 0;
        for (const img of document.querySelectorAll('img')) {
            const r = img.getBoundingClientRect();
            if (r.x > 1050 && r.y > 80 && r.width > 40 && r.height > 40) c++;
        }
        return c;
    }""")


def map_panel(page, label=""):
    """Map visible items in the left panel area."""
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
    """Check for sidebar icons at x < 80."""
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
    """Wait for new results to appear."""
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
    print(f"  Timed out after {timeout_s}s")
    ss(page, f"gen_timeout_{label}")
    return False


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)
    print(f"  Pages: {len(context.pages)}")

    # Navigate to the Dzine canvas
    page = context.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    print("  Navigating to Dzine canvas...")
    page.goto("https://www.dzine.ai/canvas?id=19797967",
              wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(8000)  # Wait for canvas to fully load

    # Close any dialogs
    close_all_dialogs(page)
    page.wait_for_timeout(2000)
    close_all_dialogs(page)  # Double pass for nested dialogs
    page.wait_for_timeout(1000)

    ss(page, "canvas_loaded")

    try:
        # Verify sidebar
        sidebar = verify_sidebar(page)
        print(f"\n  Sidebar ({len(sidebar)} items):")
        for s in sidebar:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text']}'")

        if not sidebar:
            print("  Sidebar not visible. Waiting more...")
            page.wait_for_timeout(5000)
            close_all_dialogs(page)
            sidebar = verify_sidebar(page)
            print(f"  Sidebar after extra wait ({len(sidebar)}):")
            for s in sidebar:
                print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text']}'")

        if not sidebar:
            print("  FATAL: No sidebar after extended wait")
            ss(page, "no_sidebar")
            # Try to see what IS on the page
            all_vis = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    if (rect.width > 20 && rect.height > 10 && text && text.length > 2 &&
                        text.length < 60 && el.children.length < 3) {
                        items.push({text, x: Math.round(rect.x), y: Math.round(rect.y)});
                    }
                }
                const seen = new Set();
                return items.filter(i => { if (seen.has(i.text)) return false; seen.add(i.text); return true; })
                           .sort((a, b) => a.y - b.y).slice(0, 30);
            }""")
            print("  Visible elements:")
            for v in all_vis:
                print(f"    ({v['x']},{v['y']}) '{v['text']}'")
            return

        # Build position map
        sidebar_pos = {}
        for s in sidebar:
            sidebar_pos[s['text']] = (s['x'] + s['w']//2, s['y'] + s['h']//2)

        # ================================================================
        # PART 1: TXT2IMG GENERATION (20 credits) — Simplest approach
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 1: TXT2IMG GENERATION (20 credits)")
        print("=" * 60)

        txt_pos = None
        for key in sidebar_pos:
            if "Txt2Img" in key or "Txt" in key:
                txt_pos = sidebar_pos[key]
                break

        if txt_pos:
            print(f"\n  Clicking Txt2Img at {txt_pos}...")
            page.mouse.click(*txt_pos)
            page.wait_for_timeout(2000)
            close_all_dialogs(page)
            ss(page, "txt2img_panel")
            panel = map_panel(page, "Txt2Img Panel")

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
                ss(page, "txt2img_prompt")
                print(f"  Typed prompt ({len(prompt)} chars)")

                # Check settings visible in the panel
                style_info = page.evaluate("""() => {
                    const info = {};
                    for (const el of document.querySelectorAll('*')) {
                        const text = (el.innerText || '').trim();
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 500 && rect.y > 50 && rect.y < 900) {
                            if (text.match(/^(Nano|Banana|Mochi|Real|Anime)/)) {
                                info.style = text.substring(0, 40);
                            }
                            if (['1K','2K','4K'].includes(text)) {
                                info.quality = text;
                            }
                            if (text.match(/^\\d+:\\d+$/) || text.match(/^(Portrait|Landscape|Square|Default)/)) {
                                info.ratio = text;
                            }
                        }
                    }
                    return info;
                }""")
                print(f"  Settings: {style_info}")

                # Count results before generating
                initial = count_results(page)
                print(f"  Results before: {initial}")

                # Find and click Generate button
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
                    print("  CLICKING GENERATE!")
                    page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
                    page.wait_for_timeout(1000)
                    ss(page, "txt2img_clicked_gen")

                    # Check for errors/popups
                    page.wait_for_timeout(2000)
                    close_all_dialogs(page)

                    # Wait for generation
                    success = wait_for_generation(page, initial, timeout_s=120, label="txt2img")
                    if success:
                        new_count = count_results(page)
                        print(f"  SUCCESS! {new_count} results (was {initial})")

                        # Get the latest result URL
                        latest = page.evaluate("""() => {
                            const imgs = [];
                            for (const img of document.querySelectorAll('img')) {
                                const r = img.getBoundingClientRect();
                                if (r.x > 1050 && r.y > 80 && r.width > 40 && r.height > 40) {
                                    imgs.push({src: img.src, x: r.x, y: r.y,
                                               w: Math.round(r.width), h: Math.round(r.height)});
                                }
                            }
                            return imgs[0] || null;  // First = most recent at top
                        }""")
                        if latest:
                            print(f"  Latest result: {latest['w']}x{latest['h']}")
                            print(f"  URL: {latest['src'][:120]}")
                else:
                    print("  Generate button not found. Panel state:")
                    ss(page, "txt2img_no_gen")
            else:
                print("  Prompt element not found")
                ss(page, "txt2img_no_prompt")
        else:
            print("  Txt2Img not in sidebar")

        # Close panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # ================================================================
        # PART 2: CONSISTENT CHARACTER (4 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 2: CONSISTENT CHARACTER (4 credits)")
        print("=" * 60)

        char_pos = None
        for key in sidebar_pos:
            if "Character" in key:
                char_pos = sidebar_pos[key]
                break

        if char_pos:
            print(f"\n  Clicking Character at {char_pos}...")
            page.mouse.click(*char_pos)
            page.wait_for_timeout(2000)
            close_all_dialogs(page)
            ss(page, "character_panel")
            panel = map_panel(page, "Character Panel")

            # Click "Generate Images"
            gen_found = False
            for item in panel:
                if "Generate Images" in item["text"]:
                    print(f"  Clicking '{item['text']}' at ({item['x']},{item['y']})")
                    page.mouse.click(item["x"] + item["w"]//2, item["y"] + item["h"]//2)
                    gen_found = True
                    break

            if not gen_found:
                # Try JS click
                gen_found = page.evaluate("""() => {
                    for (const el of document.querySelectorAll('button, div, span, a')) {
                        const text = (el.innerText || '').trim();
                        const rect = el.getBoundingClientRect();
                        if (text === 'Generate Images' && rect.x > 60 && rect.x < 500 &&
                            rect.width > 0 && rect.height > 0) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")

            page.wait_for_timeout(2000)
            close_all_dialogs(page)
            ss(page, "cc_panel")
            cc_panel = map_panel(page, "Consistent Character Panel")

            # Check if Ray character is auto-selected
            ray_selected = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    if (text.includes('Ray') && el.getBoundingClientRect().x > 60 &&
                        el.getBoundingClientRect().x < 500) {
                        return text.substring(0, 60);
                    }
                }
                return null;
            }""")
            print(f"\n  Ray character: {ray_selected}")

            # Find textarea for scene/action
            textarea = page.evaluate("""() => {
                for (const el of document.querySelectorAll('textarea')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 500 && rect.width > 100 && rect.height > 20) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                                placeholder: el.placeholder || ''};
                    }
                }
                return null;
            }""")
            print(f"  Textarea: {textarea}")

            if textarea:
                page.mouse.click(textarea["x"] + 50, textarea["y"] + 10)
                page.wait_for_timeout(300)
                page.keyboard.press("Meta+a")
                page.wait_for_timeout(100)

                scene = "Standing behind a modern desk in a minimalist studio, one hand resting on desk, confident smile, looking directly at camera, soft studio lighting, clean white background"
                page.keyboard.type(scene, delay=5)
                page.wait_for_timeout(500)
                ss(page, "cc_typed")

                # Count and generate
                initial = count_results(page)

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
                    print("  CLICKING GENERATE!")
                    page.mouse.click(gen_btn["x"] + gen_btn["w"]//2, gen_btn["y"] + gen_btn["h"]//2)
                    page.wait_for_timeout(1000)
                    ss(page, "cc_generating")

                    page.wait_for_timeout(2000)
                    close_all_dialogs(page)

                    success = wait_for_generation(page, initial, timeout_s=90, label="cc")
                    if success:
                        print(f"  CC Generation succeeded! Results: {count_results(page)}")
            else:
                print("  No textarea found in CC panel")
                ss(page, "cc_no_textarea")
        else:
            print("  Character not in sidebar")

        # Close panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # ================================================================
        # PART 3: CHAT EDITOR (20 credits)
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 3: CHAT EDITOR (20 credits)")
        print("=" * 60)

        # Deselect everything
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Map bottom area to find chat editor
        bottom = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 750 && rect.y < 900 && rect.x > 100 && rect.x < 1100 &&
                    rect.width > 30 && rect.height > 10 && el.children.length < 5) {
                    const text = (el.innerText || '').trim();
                    const cls = (el.className || '').toString().substring(0, 30);
                    const ce = el.contentEditable === 'true';
                    const ta = el.tagName === 'TEXTAREA';
                    if (text || ce || ta) {
                        items.push({text: text.substring(0, 60), tag: el.tagName, cls, ce, ta,
                                   x: Math.round(rect.x), y: Math.round(rect.y),
                                   w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 20);
        }""")
        print(f"\n  Bottom area elements:")
        for item in bottom:
            flags = []
            if item['ce']: flags.append("CE")
            if item['ta']: flags.append("TA")
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> [{','.join(flags)}] {item['text'][:40]}")
        ss(page, "bottom_area")

        # Try clicking the chat bar area
        chat_input = None
        for y_try in [860, 850, 870, 840, 880]:
            page.mouse.click(500, y_try)
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
                print(f"  Found chat input at y={y_try}!")
                break

        if chat_input:
            print(f"  Chat input: {chat_input}")
            page.mouse.click(chat_input["x"] + 50, chat_input["y"] + chat_input["h"]//2)
            page.wait_for_timeout(300)

            prompt = "Ray, young adult male YouTuber with light skin and short dark hair, charcoal gray t-shirt. Standing in a clean modern studio holding a product box, showing it to camera with enthusiastic expression. Minimalist white background, soft lighting. Medium shot waist up. Photorealistic, 4K."
            page.keyboard.type(prompt, delay=3)
            page.wait_for_timeout(500)
            ss(page, "chat_typed")
            print(f"  Typed prompt ({len(prompt)} chars)")

            initial = count_results(page)

            gen_btn = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.y > 500 && !btn.disabled && rect.width > 30) {
                        return {text: text.substring(0, 40), x: rect.x, y: rect.y,
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
                ss(page, "chat_generating")
                page.wait_for_timeout(2000)
                close_all_dialogs(page)
                success = wait_for_generation(page, initial, timeout_s=120, label="chat")
                if success:
                    print(f"  Chat generation succeeded! Results: {count_results(page)}")
        else:
            print("  Chat editor not found via clicking. Trying direct navigation to chat bar...")
            ss(page, "chat_not_found")

        # ================================================================
        # PART 4: EXPLORE GENERATED RESULTS + ACTIONS
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 4: RESULT ACTIONS")
        print("=" * 60)

        results = page.evaluate("""() => {
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
        print(f"\n  {len(results)} result images")

        if results:
            first = results[0]
            # Hover to reveal action buttons
            page.mouse.move(first["x"] + first["w"]//2, first["y"] + first["h"]//2)
            page.wait_for_timeout(1000)

            # Map hover actions
            hover_btns = page.evaluate("""(imgRect) => {
                const btns = [];
                for (const el of document.querySelectorAll('button, [role="button"], div')) {
                    const rect = el.getBoundingClientRect();
                    // Look for small buttons near/overlapping the image
                    if (rect.x > imgRect.x - 10 && rect.x < imgRect.x + imgRect.w + 10 &&
                        rect.y > imgRect.y - 10 && rect.y < imgRect.y + imgRect.h + 50 &&
                        rect.width > 5 && rect.width < 100 && rect.height > 5 && rect.height < 60) {
                        const text = (el.title || el.getAttribute('aria-label') || el.innerText || '').trim();
                        const svg = !!el.querySelector('svg');
                        if (text || svg) {
                            btns.push({text: text.substring(0, 30), x: Math.round(rect.x),
                                      y: Math.round(rect.y), w: Math.round(rect.width),
                                      h: Math.round(rect.height), svg});
                        }
                    }
                }
                const seen = new Set();
                return btns.filter(b => {
                    const key = `${b.x},${b.y}`;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                });
            }""", {"x": first["x"], "y": first["y"], "w": first["w"], "h": first["h"]})

            print(f"  Hover action buttons:")
            for b in hover_btns:
                print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} '{b['text']}' svg={b['svg']}")
            ss(page, "result_hover_actions")

            # Also look for context menu / extended action buttons below the result
            ext_actions = page.evaluate("""(imgRect) => {
                const items = [];
                for (const el of document.querySelectorAll('button, [role="button"]')) {
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    if (rect.x > 1050 && rect.y > imgRect.y + imgRect.h &&
                        rect.y < imgRect.y + imgRect.h + 300 && text.length > 2 &&
                        text.length < 40 && rect.width > 30) {
                        items.push({text, x: Math.round(rect.x), y: Math.round(rect.y),
                                   w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
                return items;
            }""", {"x": first["x"], "y": first["y"], "w": first["w"], "h": first["h"]})

            print(f"\n  Extended action buttons below result:")
            for a in ext_actions:
                print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} '{a['text']}'")

        # ================================================================
        # PART 5: CREDITS + SUMMARY
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 5: CREDITS + SUMMARY")
        print("=" * 60)

        credits_text = page.evaluate("""() => {
            const results = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.y < 40 && rect.x > 800 && rect.width > 0 && text.length > 0 && text.length < 30) {
                    results.push({text, x: Math.round(rect.x)});
                }
            }
            const seen = new Set();
            return results.filter(r => { if (seen.has(r.text)) return false; seen.add(r.text); return true; })
                         .sort((a, b) => a.x - b.x);
        }""")
        print(f"\n  Top bar info:")
        for c in credits_text:
            print(f"    x={c['x']} '{c['text']}'")

        total = count_results(page)
        print(f"\n  Total results: {total}")
        ss(page, "final")

        print("\n\n===== PHASE 16 COMPLETE =====")

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
