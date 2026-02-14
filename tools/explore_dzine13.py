"""Phase 13: Close tutorial dialog, set viewport, explore all tools properly.

Fixed: Tutorial dialog was blocking UI. Sidebar was at negative x due to overlay.
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
    path = OUT_DIR / f"G{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: G{_N:02d}_{name}")


def close_all_dialogs(page):
    """Close popups, tutorials, previews, and other blocking overlays."""
    for _ in range(5):
        found = False
        # "Not now" popup
        try:
            btn = page.locator('button:has-text("Not now")')
            if btn.count() > 0 and btn.first.is_visible(timeout=500):
                btn.first.click()
                page.wait_for_timeout(500)
                found = True
        except Exception:
            pass
        # "Close" button (tutorial dialogs)
        try:
            btn = page.locator('button:has-text("Close")')
            if btn.count() > 0 and btn.first.is_visible(timeout=500):
                btn.first.click()
                page.wait_for_timeout(500)
                found = True
        except Exception:
            pass
        # "Never show again"
        try:
            btn = page.locator('button:has-text("Never show again")')
            if btn.count() > 0 and btn.first.is_visible(timeout=500):
                btn.first.click()
                page.wait_for_timeout(500)
                found = True
        except Exception:
            pass
        # Escape
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
        if not found:
            break


def map_panel(page, label=""):
    """Map visible items in the left panel (x: 60-400)."""
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
    return page.evaluate("""() => {
        let c = 0;
        for (const img of document.querySelectorAll('img')) {
            const r = img.getBoundingClientRect();
            if (r.x > 1050 && r.y > 80 && r.width > 40 && r.height > 40) c++;
        }
        return c;
    }""")


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
        page.goto("https://www.dzine.ai/canvas?id=19797967",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

    # CRITICAL: Set viewport on existing page
    page.set_viewport_size({"width": 1440, "height": 900})
    page.bring_to_front()
    page.wait_for_timeout(2000)

    # Close ALL blocking dialogs
    close_all_dialogs(page)
    page.wait_for_timeout(1000)
    ss(page, "start")

    try:
        # ===== Verify sidebar is visible =====
        print("\n===== VERIFY SIDEBAR =====")
        sidebar_check = page.evaluate("""() => {
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
        print(f"Sidebar items ({len(sidebar_check)}):")
        for s in sidebar_check:
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text']}'")

        if not sidebar_check:
            print("\n  Sidebar NOT visible — reloading page...")
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            close_all_dialogs(page)
            page.wait_for_timeout(1000)
            ss(page, "after_reload")

            sidebar_check = page.evaluate("""() => {
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
            print(f"Sidebar after reload ({len(sidebar_check)}):")
            for s in sidebar_check:
                print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text']}'")

        # Build a sidebar position map
        sidebar_pos = {}
        for s in sidebar_check:
            sidebar_pos[s['text']] = (s['x'] + s['w']//2, s['y'] + s['h']//2)

        # ===== Click layer to select it =====
        print("\n===== SELECT LAYER =====")
        # Click center of canvas where Ray's image should be
        page.mouse.click(700, 450)
        page.wait_for_timeout(1000)
        ss(page, "layer_selected")

        # ===== EXPLORE EACH SIDEBAR TOOL =====
        tools_to_explore = [
            "Txt2Img", "Img2Img", "Character", "AI Video", "Lip Sync",
            "Video Editor", "Motion Control", "Enhance", "Image Editor", "Instant"
        ]

        for tool_name in tools_to_explore:
            print(f"\n{'='*50}")
            print(f"  TOOL: {tool_name}")
            print(f"{'='*50}")

            # Find the tool in sidebar positions
            pos = None
            for key, val in sidebar_pos.items():
                if key.startswith(tool_name) or tool_name in key:
                    pos = val
                    break

            if pos:
                print(f"  Clicking at ({pos[0]}, {pos[1]})")
                page.mouse.click(pos[0], pos[1])
                page.wait_for_timeout(2000)
                close_all_dialogs(page)
                page.wait_for_timeout(500)
                ss(page, tool_name.replace(" ", "_").lower())
                map_panel(page, tool_name)
            else:
                print(f"  Position not found for '{tool_name}'")
                # Try JS click
                page.evaluate(f"""() => {{
                    for (const el of document.querySelectorAll('*')) {{
                        const text = (el.innerText || '').trim();
                        const rect = el.getBoundingClientRect();
                        if (text.startsWith('{tool_name}') && rect.x >= 0 && rect.x < 80 && rect.y > 40) {{
                            el.parentElement.click();
                            return;
                        }}
                    }}
                }}""")
                page.wait_for_timeout(2000)
                close_all_dialogs(page)
                ss(page, tool_name.replace(" ", "_").lower())
                map_panel(page, tool_name)

        # ===== GENERATE VIA CHAT EDITOR =====
        print(f"\n{'='*50}")
        print("  CHAT EDITOR GENERATION (20 credits)")
        print(f"{'='*50}")

        # Click empty area to deselect
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        # Click the bottom chat bar area
        page.mouse.click(700, 850)
        page.wait_for_timeout(1500)
        ss(page, "chat_bar_click")

        # Check if chat prompt is visible
        prompt = page.evaluate("""() => {
            const ce = document.querySelector('[contenteditable="true"][data-prompt="true"]');
            if (ce) {
                const rect = ce.getBoundingClientRect();
                return {found: true, x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                        visible: rect.width > 50 && rect.height > 10,
                        cls: (ce.className || '').substring(0, 40)};
            }
            // Fallback: any visible contenteditable
            for (const ce2 of document.querySelectorAll('[contenteditable="true"]')) {
                const rect = ce2.getBoundingClientRect();
                if (rect.width > 100 && rect.height > 10 && rect.y > 600) {
                    return {found: true, x: rect.x, y: rect.y, w: rect.width, h: rect.height,
                            visible: true, cls: (ce2.className || '').substring(0, 40)};
                }
            }
            return {found: false};
        }""")
        print(f"  Prompt: {prompt}")

        if prompt.get('visible'):
            # Click it and type
            page.mouse.click(prompt['x'] + 50, prompt['y'] + 10)
            page.wait_for_timeout(300)

            text = "Ray, young adult male YouTuber, light skin, short dark hair, charcoal gray t-shirt. Standing in modern minimalist studio, soft lighting, clean white background. Medium shot waist up, confident smile, facing camera. Photorealistic 4K."
            page.keyboard.type(text, delay=8)
            page.wait_for_timeout(1000)
            ss(page, "typed_prompt")

            # Click Generate
            initial = count_results(page)
            gen = page.evaluate("""() => {
                const btn = document.querySelector('#chat-editor-generate-btn');
                if (btn && !btn.disabled) {
                    const rect = btn.getBoundingClientRect();
                    btn.click();
                    return {clicked: true, x: rect.x, y: rect.y};
                }
                // Try any generate button
                for (const b of document.querySelectorAll('button')) {
                    const text = (b.innerText || '').trim();
                    const rect = b.getBoundingClientRect();
                    if (text.startsWith('Generate') && rect.y > 700 && !b.disabled) {
                        b.click();
                        return {clicked: true, x: rect.x, y: rect.y, text};
                    }
                }
                return {clicked: false};
            }""")
            print(f"  Generate: {gen}")

            if gen.get('clicked'):
                print("  Waiting for generation...")
                ss(page, "generating")
                start = time.monotonic()
                while time.monotonic() - start < 120:
                    page.wait_for_timeout(5000)
                    cur = count_results(page)
                    elapsed = time.monotonic() - start
                    if cur > initial:
                        print(f"  Done! {cur} results in {elapsed:.0f}s")
                        ss(page, "gen_complete")
                        break
                    print(f"  ... {elapsed:.0f}s")
                else:
                    print("  Timed out")
                    ss(page, "gen_timeout")
        else:
            print("  Chat prompt not visible. Trying to expand chat bar...")
            # Maybe need to click the collapsed bar differently
            chat_bar_info = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.y > 700 && rect.y < 900 && rect.x > 300 && rect.x < 900 &&
                        rect.width > 100 && rect.height > 20) {
                        const text = (el.innerText || '').trim();
                        const cls = (el.className || '').toString().substring(0, 40);
                        if (text || cls) {
                            items.push({text: text.substring(0, 60), cls, x: Math.round(rect.x),
                                       y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)});
                        }
                    }
                }
                return items.slice(0, 15);
            }""")
            print(f"  Bottom area elements:")
            for item in chat_bar_info:
                print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} [{item['cls'][:20]}] {item['text']}")

        # ===== TOP BAR PROCESSING TOOLS =====
        print(f"\n{'='*50}")
        print("  TOP PROCESSING TOOLS")
        print(f"{'='*50}")

        # Select layer first
        page.mouse.click(700, 450)
        page.wait_for_timeout(1000)

        for tool in ["AI Eraser", "Hand Repair", "Expression", "BG Remove"]:
            print(f"\n  --- {tool} ---")
            clicked = page.evaluate("""(name) => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text === name && rect.y > 30 && rect.y < 130 && rect.x > 300 && rect.width > 0) {
                        el.click();
                        return {x: rect.x, y: rect.y};
                    }
                }
                return null;
            }""", tool)

            if clicked:
                page.wait_for_timeout(1500)
                close_all_dialogs(page)
                page.wait_for_timeout(500)
                ss(page, f"top_{tool.replace(' ','_').lower()}")
                map_panel(page, tool)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            else:
                print(f"    Not found")

        print("\n\n===== PHASE 13 COMPLETE =====")

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
