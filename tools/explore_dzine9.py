"""Phase 9: Continue deep study after closing Consistent Character panel.

Key fix: The Consistent Character panel was stuck open. Close it via its
X button or back arrow before exploring other tools.
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


def ss(page, name):
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: {name}")


def close_popup(page):
    for _ in range(3):
        try:
            btn = page.locator('button:has-text("Not now")')
            if btn.count() > 0 and btn.first.is_visible(timeout=1500):
                btn.first.click()
                page.wait_for_timeout(500)
        except Exception:
            break


def close_left_panel(page):
    """Close any open left panel — handles Consistent Character, regular panels, etc."""
    # 1. Close Consistent Character panel via its X button in header
    page.evaluate("""() => {
        // Find close buttons in the panel header area (x: 60-400, y: 50-120)
        const all = document.querySelectorAll('svg, button, [class*="close"]');
        for (const el of all) {
            const rect = el.getBoundingClientRect();
            if (rect.x > 300 && rect.x < 340 && rect.y > 55 && rect.y < 80 &&
                rect.width < 30 && rect.height < 30) {
                el.click();
                return true;
            }
        }
        // Try clicking the back arrow
        const backs = document.querySelectorAll('[class*="back"], svg');
        for (const el of backs) {
            const rect = el.getBoundingClientRect();
            if (rect.x > 80 && rect.x < 120 && rect.y > 55 && rect.y < 80 &&
                rect.width < 30 && rect.height < 30) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # 2. Escape to dismiss any remaining overlays
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)


def click_sidebar(page, tool_name):
    """Click sidebar tool with robust matching."""
    close_left_panel(page)
    page.wait_for_timeout(500)

    # Use evaluate to match sidebar items precisely (x < 60 area)
    clicked = page.evaluate("""(name) => {
        const all = document.querySelectorAll('*');
        // First pass: exact match in sidebar area
        for (const el of all) {
            const rect = el.getBoundingClientRect();
            const text = (el.innerText || '').trim().replace(/\\n/g, ' ');
            if (rect.x >= 0 && rect.x < 65 && rect.width > 10 && rect.width < 70 &&
                rect.height > 10 && rect.y > 50) {
                if (text === name || text.startsWith(name + ' ') || text.startsWith(name + '\\n')) {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return {clicked: true, text, x: rect.x, y: rect.y};
                }
            }
        }
        return {clicked: false};
    }""", tool_name)

    if clicked.get("clicked"):
        print(f"  Clicked sidebar: '{tool_name}' at ({clicked['x']}, {clicked['y']})")
        page.wait_for_timeout(2000)
        return True

    # Fallback: broader text match
    loc = page.locator(f'text="{tool_name}"')
    for i in range(min(loc.count(), 5)):
        try:
            el = loc.nth(i)
            box = el.bounding_box()
            if box and box['x'] < 65:
                el.click(force=True, timeout=3000)
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue

    print(f"  Sidebar '{tool_name}' not found")
    return False


def map_panel(page, label=""):
    """Map visible panel content."""
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
                    items.push({text: text.substring(0, 80), tag: el.tagName, y: Math.round(rect.y),
                                cls: (el.className || '').toString().substring(0, 40)});
                }
            }
        }
        return items.sort((a, b) => a.y - b.y).slice(0, 40);
    }""")
    print(f"\n  {label} panel ({len(items)} items):")
    for item in items:
        print(f"    y={item['y']} <{item['tag']}> [{item['cls'][:20]}] {item['text']}")
    return items


def map_inputs(page, label=""):
    """Map interactive inputs."""
    inputs = page.evaluate("""() => {
        const items = [];
        for (const ta of document.querySelectorAll('textarea')) {
            const rect = ta.getBoundingClientRect();
            if (rect.x > 60 && rect.x < 400 && rect.width > 0)
                items.push({type: 'textarea', placeholder: ta.placeholder || '', visible: rect.width > 50,
                            cls: (ta.className || '').substring(0, 40), y: Math.round(rect.y)});
        }
        for (const ce of document.querySelectorAll('[contenteditable="true"]')) {
            const rect = ce.getBoundingClientRect();
            if (rect.x > 60 && rect.x < 400 && rect.width > 0)
                items.push({type: 'contenteditable', visible: rect.width > 50,
                            cls: (ce.className || '').substring(0, 40), y: Math.round(rect.y)});
        }
        for (const btn of document.querySelectorAll('button')) {
            const rect = btn.getBoundingClientRect();
            const text = (btn.innerText || '').trim();
            if (rect.x > 60 && rect.x < 400 && rect.width > 0 && text.includes('Generate'))
                items.push({type: 'button', text, id: btn.id || '',
                            cls: (btn.className || '').substring(0, 40), y: Math.round(rect.y)});
        }
        return items.sort((a, b) => a.y - b.y);
    }""")
    if inputs:
        print(f"\n  {label} inputs:")
        for inp in inputs:
            print(f"    {inp}")
    return inputs


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
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("https://www.dzine.ai/canvas?id=19797967",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

    page.bring_to_front()
    page.wait_for_timeout(2000)
    close_popup(page)

    try:
        # ===== STEP 0: Close stuck Consistent Character panel =====
        print("\n===== CLOSING CONSISTENT CHARACTER PANEL =====")
        close_left_panel(page)
        page.wait_for_timeout(1000)
        ss(page, "C00_clean_canvas")

        # Verify panel is closed — check if "Consistent Character" text is visible
        cc_visible = page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 100 && rect.width > 0) {
                    if ((el.innerText || '').trim().includes('Consistent Character')) return true;
                }
            }
            return false;
        }""")
        if cc_visible:
            print("  Consistent Character still showing — trying harder...")
            # Click the actual close X at the top right of the panel
            page.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    // The X close button should be around x=310, y=68, small
                    if (rect.x > 295 && rect.x < 330 && rect.y > 50 && rect.y < 90 &&
                        rect.width < 40 && rect.height < 40 && rect.width > 5) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(1000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        ss(page, "C01_after_close")

        # ===== 1. Txt2Img — Full panel exploration =====
        print("\n" + "="*60)
        print("1. Txt2Img FULL PANEL")
        print("="*60)

        if click_sidebar(page, "Txt2Img"):
            page.wait_for_timeout(1500)
            ss(page, "C02_txt2img")
            map_panel(page, "Txt2Img")
            map_inputs(page, "Txt2Img")

            # Scroll down in the panel to see Advanced
            page.evaluate("""() => {
                const panel = document.querySelector('.gen-config-form') ||
                              document.querySelector('.gen-config-body');
                if (panel) panel.scrollTop = panel.scrollHeight;
            }""")
            page.wait_for_timeout(1000)
            ss(page, "C03_txt2img_scrolled")
            map_panel(page, "Txt2Img scrolled")

        close_left_panel(page)

        # ===== 2. Img2Img — Non-Character mode =====
        print("\n" + "="*60)
        print("2. Img2Img (after closing Character)")
        print("="*60)

        if click_sidebar(page, "Img2Img"):
            page.wait_for_timeout(1500)
            ss(page, "C04_img2img")
            map_panel(page, "Img2Img")
            map_inputs(page, "Img2Img")

        close_left_panel(page)

        # ===== 3. AI Video =====
        print("\n" + "="*60)
        print("3. AI VIDEO")
        print("="*60)

        if click_sidebar(page, "AI Video"):
            page.wait_for_timeout(1500)
            ss(page, "C05_ai_video")
            map_panel(page, "AI Video")
            map_inputs(page, "AI Video")

        close_left_panel(page)

        # ===== 4. Lip Sync =====
        print("\n" + "="*60)
        print("4. LIP SYNC")
        print("="*60)

        if click_sidebar(page, "Lip Sync"):
            page.wait_for_timeout(1500)
            ss(page, "C06_lip_sync")
            map_panel(page, "Lip Sync")

            # Detailed element mapping for Lip Sync
            lip_detail = page.evaluate("""() => {
                const items = [];
                const seen = new Set();
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                        rect.width > 10 && rect.height > 5) {
                        const text = (el.innerText || '').trim();
                        const cls = (el.className || '').toString().substring(0, 50);
                        const tag = el.tagName;
                        if (text && text.length > 1 && text.length < 120 && el.children.length < 5 && !seen.has(text)) {
                            seen.add(text);
                            items.push({tag, cls, text: text.substring(0, 80), y: Math.round(rect.y)});
                        }
                    }
                }
                return items.sort((a, b) => a.y - b.y).slice(0, 30);
            }""")
            print("\n  Lip Sync detailed:")
            for item in lip_detail:
                print(f"    y={item['y']} <{item['tag']}> [{item['cls'][:25]}] {item['text']}")

        close_left_panel(page)

        # ===== 5. Video Editor =====
        print("\n" + "="*60)
        print("5. VIDEO EDITOR")
        print("="*60)

        if click_sidebar(page, "Video Editor"):
            page.wait_for_timeout(1500)
            ss(page, "C07_video_editor")
            map_panel(page, "Video Editor")

        close_left_panel(page)

        # ===== 6. Motion Control =====
        print("\n" + "="*60)
        print("6. MOTION CONTROL")
        print("="*60)

        if click_sidebar(page, "Motion Control"):
            page.wait_for_timeout(1500)
            ss(page, "C08_motion_control")
            map_panel(page, "Motion Control")

        close_left_panel(page)

        # ===== 7. Enhance & Upscale =====
        print("\n" + "="*60)
        print("7. ENHANCE & UPSCALE")
        print("="*60)

        # This is lower in sidebar — scroll first
        page.evaluate("""() => {
            const sidebar = document.querySelector('[class*="tool-list"]') ||
                           document.querySelector('[class*="sidebar-list"]');
            if (sidebar) sidebar.scrollTop = sidebar.scrollHeight;
        }""")
        page.wait_for_timeout(500)

        if click_sidebar(page, "Enhance"):
            page.wait_for_timeout(1500)
            ss(page, "C09_enhance")
            map_panel(page, "Enhance & Upscale")
            map_inputs(page, "Enhance")

        close_left_panel(page)

        # ===== 8. Image Editor =====
        print("\n" + "="*60)
        print("8. IMAGE EDITOR")
        print("="*60)

        if click_sidebar(page, "Image Editor"):
            page.wait_for_timeout(1500)
            ss(page, "C10_image_editor")
            map_panel(page, "Image Editor")

        close_left_panel(page)

        # ===== 9. Instant Storyboard =====
        print("\n" + "="*60)
        print("9. INSTANT STORYBOARD")
        print("="*60)

        if click_sidebar(page, "Instant"):
            page.wait_for_timeout(1500)
            ss(page, "C11_storyboard")
            map_panel(page, "Storyboard")
            map_inputs(page, "Storyboard")

        close_left_panel(page)

        # ===== 10. Upload tool =====
        print("\n" + "="*60)
        print("10. UPLOAD TOOL")
        print("="*60)

        # Scroll sidebar back to top
        page.evaluate("""() => {
            const sidebar = document.querySelector('[class*="tool-list"]') ||
                           document.querySelector('[class*="sidebar-list"]');
            if (sidebar) sidebar.scrollTop = 0;
        }""")
        page.wait_for_timeout(500)

        if click_sidebar(page, "Upload"):
            page.wait_for_timeout(1500)
            ss(page, "C12_upload")
            map_panel(page, "Upload")

        close_left_panel(page)

        # ===== 11. Assets tool =====
        print("\n" + "="*60)
        print("11. ASSETS TOOL")
        print("="*60)

        if click_sidebar(page, "Assets"):
            page.wait_for_timeout(1500)
            ss(page, "C13_assets")
            map_panel(page, "Assets")

        close_left_panel(page)

        # ===== 12. TOP BAR PROCESSING TOOLS =====
        print("\n" + "="*60)
        print("12. TOP BAR TOOLS")
        print("="*60)

        for tool_name in ["AI Eraser", "Hand Repair", "Expression", "BG Remove"]:
            print(f"\n  --- {tool_name} ---")
            try:
                clicked = page.evaluate("""(name) => {
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        const text = (el.innerText || '').trim();
                        if (text === name && rect.y > 70 && rect.y < 120 && rect.x > 350 && rect.x < 1000) {
                            el.click();
                            return {x: rect.x, y: rect.y};
                        }
                    }
                    return null;
                }""", tool_name)
                if clicked:
                    print(f"    Clicked at ({clicked['x']}, {clicked['y']})")
                    page.wait_for_timeout(1500)
                    ss(page, f"C14_{tool_name.replace(' ', '_').lower()}")

                    # Map what appeared
                    tool_items = page.evaluate("""() => {
                        const items = [];
                        const seen = new Set();
                        for (const el of document.querySelectorAll('*')) {
                            const rect = el.getBoundingClientRect();
                            if (rect.x > 60 && rect.x < 500 && rect.y > 50 && rect.y < 700 &&
                                rect.width > 20 && rect.height > 5) {
                                const text = (el.innerText || '').trim();
                                if (text && text.length > 1 && text.length < 100 &&
                                    el.children.length < 4 && !seen.has(text)) {
                                    seen.add(text);
                                    items.push(text.substring(0, 60));
                                }
                            }
                        }
                        return items.slice(0, 15);
                    }""")
                    for t in tool_items:
                        print(f"    {t}")

                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                else:
                    print(f"    Not found")
            except Exception as exc:
                print(f"    Error: {exc}")

        # ===== 13. TOP BAR ICON ROW =====
        print("\n" + "="*60)
        print("13. TOP ICON ROW (above canvas)")
        print("="*60)

        top_icons = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('button, [role="button"], svg, img')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 70 && rect.y < 120 && rect.x > 700 && rect.x < 1100 &&
                    rect.width > 10 && rect.width < 60) {
                    const title = el.getAttribute('title') || '';
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    const cls = (el.className || '').toString().substring(0, 40);
                    const text = (el.innerText || '').trim();
                    items.push({x: Math.round(rect.x), title, ariaLabel, cls, text: text.substring(0, 20)});
                }
            }
            return items.sort((a, b) => a.x - b.x);
        }""")
        print(f"  Top icons ({len(top_icons)}):")
        for ic in top_icons:
            ident = ic['title'] or ic['ariaLabel'] or ic['text'] or ic['cls'][:25]
            print(f"    @{ic['x']}px: {ident}")

        # ===== 14. LAYERS PANEL =====
        print("\n" + "="*60)
        print("14. LAYERS PANEL")
        print("="*60)

        layers_tab = page.locator('text="Layers"')
        if layers_tab.count() > 0:
            try:
                layers_tab.first.click(force=True, timeout=3000)
                page.wait_for_timeout(1500)
                ss(page, "C15_layers")

                layer_items = page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    // Right panel area (x > 1050)
                    for (const el of document.querySelectorAll('*')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 1050 && rect.y > 80 && rect.width > 20) {
                            const text = (el.innerText || '').trim();
                            const cls = (el.className || '').toString().substring(0, 40);
                            if (text && text.length > 1 && text.length < 80 && el.children.length < 4 && !seen.has(text)) {
                                seen.add(text);
                                items.push({text, cls, y: Math.round(rect.y)});
                            }
                        }
                    }
                    return items.sort((a, b) => a.y - b.y).slice(0, 20);
                }""")
                for l in layer_items:
                    print(f"    [{l['cls'][:15]}] {l['text']}")
            except Exception as exc:
                print(f"  Layers error: {exc}")

        # Switch back to Results
        results_tab = page.locator('text="Results"')
        if results_tab.count() > 0:
            try:
                results_tab.first.click(force=True, timeout=3000)
                page.wait_for_timeout(500)
            except Exception:
                pass

        # ===== 15. CANVAS SIZE DIALOG =====
        print("\n" + "="*60)
        print("15. CANVAS SIZE DIALOG")
        print("="*60)

        # The size is shown in the top-left as "1536 x 1536" or similar
        size_clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (rect.y < 50 && rect.x > 50 && rect.x < 250 && text.match(/\\d+\\s*[×x]\\s*\\d+/)) {
                    el.click();
                    return text;
                }
            }
            return null;
        }""")
        if size_clicked:
            print(f"  Clicked size: {size_clicked}")
            page.wait_for_timeout(2000)
            ss(page, "C16_size_dialog")

            # Map the dialog
            size_opts = page.evaluate("""() => {
                const items = [];
                const seen = new Set();
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.y > 0 && rect.y < 600 && rect.width > 20) {
                        const text = (el.innerText || '').trim();
                        if (text && text.length > 1 && text.length < 60 &&
                            (text.includes(':') || text.includes('Custom') || text.includes('Apply') ||
                             text.includes('Cancel') || text.match(/\\d+/)) &&
                            !seen.has(text)) {
                            seen.add(text);
                            items.push(text);
                        }
                    }
                }
                return items.slice(0, 20);
            }""")
            for s in size_opts:
                print(f"    {s}")

            # Cancel
            page.evaluate("""() => {
                for (const el of document.querySelectorAll('button')) {
                    if ((el.innerText || '').includes('Cancel')) { el.click(); return; }
                }
            }""")
            page.wait_for_timeout(500)

        # ===== 16. EXPORT BUTTON =====
        print("\n" + "="*60)
        print("16. EXPORT")
        print("="*60)

        export_state = page.evaluate("""() => {
            for (const el of document.querySelectorAll('button')) {
                const text = (el.innerText || '').trim();
                if (text === 'Export') {
                    return {found: true, disabled: el.disabled || el.classList.contains('disabled'),
                            cls: (el.className || '').substring(0, 40)};
                }
            }
            return {found: false};
        }""")
        print(f"  Export: {export_state}")

        # ===== 17. BOTTOM BAR CHAT EDITOR =====
        print("\n" + "="*60)
        print("17. BOTTOM BAR CHAT EDITOR")
        print("="*60)

        # Make sure no left panel is open (which hides the chat editor)
        close_left_panel(page)
        page.wait_for_timeout(1000)

        chat_elements = page.evaluate("""() => {
            const items = [];
            // Bottom area (y > 750)
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 700 && rect.x > 400 && rect.x < 1000 && rect.width > 20 && rect.height > 5) {
                    const text = (el.innerText || '').trim();
                    const cls = (el.className || '').toString().substring(0, 50);
                    const tag = el.tagName;
                    const ce = el.getAttribute('contenteditable');
                    const ph = el.getAttribute('data-placeholder') || el.placeholder || '';
                    if ((text || ce || ph) && text.length < 100) {
                        items.push({tag, cls, text: text.substring(0, 60), ce, ph,
                                   x: Math.round(rect.x), y: Math.round(rect.y),
                                   w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 20);
        }""")
        print(f"\n  Chat editor elements:")
        for el in chat_elements:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> [{el['cls'][:20]}] text={el['text']!r} ce={el['ce']} ph={el['ph']!r}")

        # Model selector
        model_info = page.evaluate("""() => {
            for (const el of document.querySelectorAll('button, [role="button"]')) {
                const cls = (el.className || '').toString();
                if (cls.includes('option-btn')) {
                    return {text: (el.innerText || '').trim(), cls: cls.substring(0, 50)};
                }
            }
            return null;
        }""")
        if model_info:
            print(f"\n  Current model: {model_info['text']}")

        # ===== 18. RESULT ACTIONS IN RIGHT PANEL =====
        print("\n" + "="*60)
        print("18. RIGHT PANEL — RESULT ACTIONS")
        print("="*60)

        # Switch to Results tab
        results_tab = page.locator('text="Results"')
        if results_tab.count() > 0:
            results_tab.first.click(force=True, timeout=3000)
            page.wait_for_timeout(1000)

        result_panel = page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 1050 && rect.y > 80 && rect.width > 20) {
                    const text = (el.innerText || '').trim();
                    const cls = (el.className || '').toString().substring(0, 40);
                    const tag = el.tagName;
                    if (text && text.length > 1 && text.length < 100 && el.children.length < 5 && !seen.has(text)) {
                        seen.add(text);
                        items.push({tag, cls, text: text.substring(0, 60), y: Math.round(rect.y)});
                    }
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 30);
        }""")
        print(f"\n  Right panel results ({len(result_panel)}):")
        for rp in result_panel:
            print(f"    y={rp['y']} <{rp['tag']}> [{rp['cls'][:15]}] {rp['text']}")

        print("\n\n" + "="*60)
        print("PHASE 9 COMPLETE")
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
