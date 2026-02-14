"""Phase 8: Deep-dive continuation — Character Generate, Img2Img, Txt2Img Advanced,
AI Video, Lip Sync, lower sidebar tools, top processing tools.

Fixes from Phase 7: no go_back(), close overlays with X/Escape, robust sidebar clicks.
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
                continue
        except Exception:
            pass
        break


def close_all_overlays(page):
    """Aggressively close any overlay blocking the workspace."""
    # 1. Promotional popup
    close_popup(page)
    # 2. Any modal with X close button
    for _ in range(3):
        try:
            x_btns = page.locator('.close-btn, [class*="close"]:not(button.export), button:has(svg[viewBox]):visible')
            for i in range(min(x_btns.count(), 5)):
                try:
                    el = x_btns.nth(i)
                    rect = el.evaluate("e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }")
                    # Only close small buttons (close icons) that are visible
                    if rect['w'] < 50 and rect['w'] > 0 and rect['h'] < 50 and rect['h'] > 0:
                        pass  # Don't auto-close everything, too aggressive
                except Exception:
                    pass
        except Exception:
            pass
        break
    # 3. Escape key to dismiss overlays
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass
    # 4. Close result preview
    try:
        preview = page.locator('#result-preview')
        if preview.count() > 0 and preview.first.is_visible(timeout=500):
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
    except Exception:
        pass
    # 5. Close character manager popup
    try:
        char_close = page.locator('[class*="character"] .close, [class*="character"] button:has(svg):near(text="Character")')
        if char_close.count() > 0:
            pass  # Don't auto-close, we handle this explicitly
    except Exception:
        pass


def click_sidebar_tool(page, tool_name):
    """Click a left sidebar tool by its visible label text."""
    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Use JS to find and click the sidebar item (avoids CSS selector issues)
    clicked = page.evaluate("""(name) => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const rect = el.getBoundingClientRect();
            // Sidebar is x < 70, tool labels are small text elements
            if (rect.x < 70 && rect.width > 0 && rect.height > 0) {
                const text = (el.innerText || '').trim().replace(/\\n/g, ' ');
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
        return True

    # Fallback: Playwright text selector
    loc = page.locator(f'text="{tool_name}"')
    if loc.count() > 0:
        try:
            loc.first.evaluate("e => e.scrollIntoView({block: 'center'})")
            page.wait_for_timeout(300)
            loc.first.click(force=True, timeout=5000)
            page.wait_for_timeout(2000)
            return True
        except Exception as exc:
            print(f"  Sidebar click '{tool_name}' fallback failed: {exc}")

    print(f"  Sidebar tool '{tool_name}' not found")
    return False


def close_left_panel(page):
    """Close any open left panel by clicking its X button."""
    try:
        # The panel header has a close X button
        close_btn = page.locator('.gen-config-header .close, .panel-header .close, .gen-config button.close')
        if close_btn.count() > 0:
            close_btn.first.click(force=True)
            page.wait_for_timeout(500)
            return
    except Exception:
        pass
    # Try the X near the panel title
    try:
        x = page.locator('[class*="panel"] svg[class*="close"], .panel-close')
        if x.count() > 0:
            x.first.click(force=True)
            page.wait_for_timeout(500)
    except Exception:
        pass


def map_panel_items(page, label=""):
    """Map all visible items in the left panel area (x: 60-400)."""
    items = page.evaluate("""() => {
        const items = [];
        const seen = new Set();
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const rect = el.getBoundingClientRect();
            if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.width > 20 && rect.height > 5) {
                const text = (el.innerText || '').trim();
                if (text && text.length < 120 && text.length > 1 && el.children.length < 4 && !seen.has(text)) {
                    seen.add(text);
                    items.push({text, tag: el.tagName, y: Math.round(rect.y)});
                }
            }
        }
        return items.sort((a, b) => a.y - b.y).slice(0, 50);
    }""")
    print(f"\n  {label} panel ({len(items)} items):")
    for item in items:
        print(f"    <{item['tag']}> {item['text'][:80]}")
    return items


def map_inputs(page, label=""):
    """Map all interactive inputs in the panel."""
    inputs = page.evaluate("""() => {
        const items = [];
        const panel = document.querySelector('.gen-config-form') || document.querySelector('.gen-config-body');
        const scope = panel || document;

        for (const ta of scope.querySelectorAll('textarea')) {
            items.push({type: 'textarea', placeholder: ta.placeholder || '', maxLength: ta.maxLength || 0,
                        visible: ta.offsetWidth > 0, cls: (ta.className || '').substring(0, 40)});
        }
        for (const ce of scope.querySelectorAll('[contenteditable="true"]')) {
            items.push({type: 'contenteditable', placeholder: ce.getAttribute('data-placeholder') || '',
                        visible: ce.offsetWidth > 0, cls: (ce.className || '').substring(0, 40)});
        }
        for (const s of scope.querySelectorAll('input[type="range"], [role="slider"]')) {
            const label = s.getAttribute('aria-label') || s.closest('[class*="config"]')?.querySelector('label, .label, .title')?.innerText || '';
            items.push({type: 'slider', label: label.substring(0, 40), value: s.value || '', min: s.min || '', max: s.max || ''});
        }
        for (const t of scope.querySelectorAll('[role="switch"], .switch, [class*="toggle"]')) {
            const label = t.closest('[class*="config"]')?.querySelector('.label, .title')?.innerText || t.previousElementSibling?.innerText || '';
            const checked = t.classList.contains('active') || t.getAttribute('aria-checked') === 'true';
            items.push({type: 'toggle', label: label.substring(0, 40), checked});
        }
        for (const f of scope.querySelectorAll('input[type="file"]')) {
            items.push({type: 'file', accept: f.accept || '', cls: (f.className || '').substring(0, 40)});
        }
        for (const n of scope.querySelectorAll('input[type="number"]')) {
            items.push({type: 'number', value: n.value || '', placeholder: n.placeholder || ''});
        }
        // Buttons
        for (const b of scope.querySelectorAll('button[class*="generate"], button[id*="generate"]')) {
            items.push({type: 'generate_btn', id: b.id || '', text: (b.innerText || '').trim().substring(0, 30),
                        cls: (b.className || '').substring(0, 40)});
        }
        return items;
    }""")
    if inputs:
        print(f"\n  {label} inputs ({len(inputs)}):")
        for inp in inputs:
            print(f"    {inp}")
    return inputs


def main():
    print("Connecting to Brave...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    # Clean up tabs
    print(f"\n  Tabs: {len(context.pages)}")
    canvas_page = None
    for p in list(context.pages):
        u = p.url
        if "canvas?id=19797967" in u:
            canvas_page = p
        elif "canvas" in u and "19797967" not in u:
            print(f"    Closing duplicate canvas: {u[:60]}")
            p.close()

    if not canvas_page:
        # Open the project with Ray
        canvas_page = context.new_page()
        canvas_page.set_viewport_size({"width": 1440, "height": 900})
        canvas_page.goto("https://www.dzine.ai/canvas?id=19797967",
                         wait_until="domcontentloaded", timeout=30000)
        canvas_page.wait_for_timeout(5000)

    page = canvas_page
    page.bring_to_front()
    page.wait_for_timeout(2000)
    close_all_overlays(page)

    try:
        # ===== 1. CHARACTER — GENERATE IMAGES WITH RAY =====
        print("\n" + "="*60)
        print("1. CHARACTER — GENERATE IMAGES WITH RAY")
        print("="*60)

        if click_sidebar_tool(page, "Character"):
            page.wait_for_timeout(1000)
            ss(page, "B01_character_panel")

            # Click "Generate Images" — use JS to target only visible left-panel items
            gen_clicked = page.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
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
                ss(page, "B02_generate_with_char")
                map_panel_items(page, "Generate with Character")
                map_inputs(page, "Generate with Character")

                # Explore what options are in this panel
                gen_full = page.evaluate("""() => {
                    const items = [];
                    const all = document.querySelectorAll('*');
                    const seen = new Set();
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 900 &&
                            rect.width > 10 && rect.height > 5) {
                            const text = (el.innerText || '').trim();
                            const tag = el.tagName;
                            const cls = (el.className || '').toString().substring(0, 50);
                            const id = el.id || '';
                            if (text && text.length > 1 && text.length < 100 &&
                                el.children.length < 5 && !seen.has(text)) {
                                seen.add(text);
                                items.push({tag, cls, id, text, y: Math.round(rect.y)});
                            }
                        }
                    }
                    return items.sort((a, b) => a.y - b.y).slice(0, 40);
                }""")
                print("\n  Full Generate panel elements:")
                for item in gen_full:
                    ident = item['id'] or item['cls'][:30]
                    print(f"    y={item['y']} <{item['tag']}> [{ident}] {item['text'][:60]}")

                # Check if Ray is selected
                ray_ref = page.locator('[class*="character"] img, [class*="ref-image"] img, [class*="face"] img')
                print(f"\n  Character reference images: {ray_ref.count()}")

                # Look for character selector in the visible panel
                char_select_found = page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x > 60 && rect.x < 400 && rect.width > 30 && rect.height > 10 &&
                            ((el.innerText || '').includes('Select') || (el.className || '').toString().includes('character-select'))) {
                            return {text: (el.innerText || '').trim().substring(0, 60), x: rect.x, y: rect.y};
                        }
                    }
                    return null;
                }""")
                if char_select_found:
                    print(f"  Character selector found: {char_select_found}")
                    try:
                        page.evaluate("""() => {
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                const rect = el.getBoundingClientRect();
                                if (rect.x > 60 && rect.x < 400 && rect.width > 30 && rect.height > 10 &&
                                    ((el.innerText || '').includes('Select') || (el.className || '').toString().includes('character-select'))) {
                                    el.click();
                                    return;
                                }
                            }
                        }""")
                        page.wait_for_timeout(2000)
                        ss(page, "B03_character_select")

                        # List available characters
                        chars = page.evaluate("""() => {
                            const items = [];
                            const all = document.querySelectorAll('[class*="character"] *, [class*="char-list"] *, [class*="char-item"] *');
                            const seen = new Set();
                            for (const el of all) {
                                const text = (el.innerText || '').trim();
                                if (text && text.length > 1 && text.length < 50 && !seen.has(text)) {
                                    seen.add(text);
                                    items.push(text);
                                }
                            }
                            return items;
                        }""")
                        print(f"  Available characters:")
                        for c in chars:
                            print(f"    - {c}")

                        # Select Ray
                        ray = page.locator('text="Ray"')
                        if ray.count() > 0:
                            ray.first.click(force=True, timeout=3000)
                            page.wait_for_timeout(1500)
                            print("  Selected Ray!")

                        page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
                    except Exception as exc:
                        print(f"  Character select error: {exc}")

        # Close Character panel
        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 2. CHARACTER — INSERT CHARACTER =====
        print("\n" + "="*60)
        print("2. CHARACTER — INSERT CHARACTER")
        print("="*60)

        if click_sidebar_tool(page, "Character"):
            page.wait_for_timeout(1000)

            insert_clicked = page.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 400 && rect.width > 50 && rect.height > 20 &&
                        (el.innerText || '').trim().startsWith('Insert Character')) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            if insert_clicked:
                page.wait_for_timeout(3000)
                ss(page, "B04_insert_character")
                map_panel_items(page, "Insert Character")
                map_inputs(page, "Insert Character")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 3. CHARACTER — CHARACTER SHEET =====
        print("\n" + "="*60)
        print("3. CHARACTER — CHARACTER SHEET")
        print("="*60)

        if click_sidebar_tool(page, "Character"):
            page.wait_for_timeout(1000)

            sheet_clicked = page.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 400 && rect.width > 50 && rect.height > 20 &&
                        (el.innerText || '').trim().startsWith('Character Sheet')) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            if sheet_clicked:
                page.wait_for_timeout(3000)
                ss(page, "B05_character_sheet")
                map_panel_items(page, "Character Sheet")
                map_inputs(page, "Character Sheet")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 4. CHARACTER — GENERATE 360° VIDEO =====
        print("\n" + "="*60)
        print("4. CHARACTER — 360° VIDEO")
        print("="*60)

        if click_sidebar_tool(page, "Character"):
            page.wait_for_timeout(1000)

            v360_btn = page.locator('text="Generate 360"')
            if v360_btn.count() == 0:
                v360_btn = page.locator('text="360°"')
            if v360_btn.count() > 0:
                v360_btn.first.click(force=True, timeout=5000)
                page.wait_for_timeout(3000)
                ss(page, "B06_360_video")
                map_panel_items(page, "360° Video")
            else:
                print("  360° Video button not found, trying scroll")
                # It might be below fold in the Character submenu
                page.evaluate("""() => {
                    const items = document.querySelectorAll('[class*="character"] *, [class*="menu-item"] *');
                    for (const el of items) {
                        if ((el.innerText || '').includes('360')) {
                            el.scrollIntoView();
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(3000)
                ss(page, "B06_360_video")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 5. Img2Img DEEP DIVE =====
        print("\n" + "="*60)
        print("5. Img2Img IN DEPTH")
        print("="*60)

        if click_sidebar_tool(page, "Img2Img"):
            page.wait_for_timeout(1500)
            ss(page, "B07_img2img")
            map_panel_items(page, "Img2Img")
            map_inputs(page, "Img2Img")

            # Click Style selector
            style_btn = page.locator('.c-style button.style, .c-style .content')
            if style_btn.count() > 0:
                try:
                    style_btn.first.click(force=True, timeout=5000)
                    page.wait_for_timeout(2000)
                    ss(page, "B08_img2img_styles")

                    # Map style categories
                    style_cats = page.evaluate("""() => {
                        const items = [];
                        const seen = new Set();
                        const all = document.querySelectorAll('[class*="style"] *, [class*="category"] *, [class*="tab"] *');
                        for (const el of all) {
                            const text = (el.innerText || '').trim();
                            if (text && text.length > 1 && text.length < 50 && !seen.has(text)) {
                                seen.add(text);
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0) items.push({text, y: Math.round(rect.y), x: Math.round(rect.x)});
                            }
                        }
                        return items.sort((a, b) => a.y - b.y).slice(0, 30);
                    }""")
                    print("\n  Style categories/items:")
                    for s in style_cats:
                        print(f"    ({s['x']},{s['y']}) {s['text']}")

                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                except Exception as exc:
                    print(f"  Style picker error: {exc}")

            # Explore Advanced settings
            adv = page.locator('text="Advanced"')
            if adv.count() > 0:
                try:
                    adv.first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1500)
                    ss(page, "B09_img2img_advanced")

                    # Map advanced options in detail
                    adv_items = page.evaluate("""() => {
                        const items = [];
                        const seen = new Set();
                        // Look for config form items
                        const form = document.querySelector('.gen-config-form') || document;
                        const all = form.querySelectorAll('*');
                        for (const el of all) {
                            const rect = el.getBoundingClientRect();
                            if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.width > 10) {
                                const text = (el.innerText || '').trim();
                                const cls = (el.className || '').toString().substring(0, 50);
                                if (text && text.length > 1 && text.length < 100 && el.children.length < 3 && !seen.has(text)) {
                                    seen.add(text);
                                    items.push({text, cls, tag: el.tagName, y: Math.round(rect.y)});
                                }
                            }
                        }
                        return items.sort((a, b) => a.y - b.y).slice(0, 40);
                    }""")
                    print("\n  Advanced settings:")
                    for item in adv_items:
                        print(f"    <{item['tag']}> [{item['cls'][:25]}] {item['text'][:60]}")

                    map_inputs(page, "Img2Img Advanced")
                except Exception as exc:
                    print(f"  Advanced error: {exc}")

            # Check for "Describe Canvas" feature
            desc = page.locator('text="Describe Canvas", text="Describe the Canvas"')
            if desc.count() > 0:
                print(f"\n  'Describe Canvas' feature found!")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 6. Txt2Img ADVANCED =====
        print("\n" + "="*60)
        print("6. Txt2Img ADVANCED SETTINGS")
        print("="*60)

        if click_sidebar_tool(page, "Txt2Img"):
            page.wait_for_timeout(1500)

            # Scroll down to find Advanced
            adv2_clicked = page.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    if (text === 'Advanced' && rect.x > 60 && rect.x < 400 && rect.width > 20) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            if adv2_clicked:
                try:
                    page.wait_for_timeout(1500)
                    ss(page, "B10_txt2img_advanced")
                    map_panel_items(page, "Txt2Img Advanced")
                    map_inputs(page, "Txt2Img Advanced")
                except Exception as exc:
                    print(f"  Txt2Img Advanced error: {exc}")

            # Check Prompt Improver
            improver = page.locator('text="Prompt Improver"')
            if improver.count() > 0:
                print("\n  Prompt Improver toggle found!")
                # Check its state
                toggle = page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        if ((el.innerText || '').includes('Prompt Improver') && el.children.length < 5) {
                            const toggle = el.querySelector('[role="switch"], [class*="switch"], [class*="toggle"]');
                            if (toggle) {
                                return {
                                    found: true,
                                    active: toggle.classList.contains('active') || toggle.getAttribute('aria-checked') === 'true'
                                };
                            }
                        }
                    }
                    return {found: false};
                }""")
                print(f"    State: {toggle}")

            # Check Face Match
            face = page.locator('text="Face Match"')
            if face.count() > 0:
                print("\n  Face Match feature found!")

            # Check Color Match
            color = page.locator('text="Color Match"')
            if color.count() > 0:
                print("\n  Color Match feature found!")

            # Check Non-Explicit
            nexp = page.locator('text="Non-Explicit"')
            if nexp.count() > 0:
                print("\n  Non-Explicit toggle found!")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 7. AI VIDEO =====
        print("\n" + "="*60)
        print("7. AI VIDEO")
        print("="*60)

        if click_sidebar_tool(page, "AI Video"):
            page.wait_for_timeout(1500)
            ss(page, "B11_ai_video")
            map_panel_items(page, "AI Video")
            map_inputs(page, "AI Video")

            # Check for video models/modes
            video_modes = page.evaluate("""() => {
                const items = [];
                const seen = new Set();
                const all = document.querySelectorAll('button, [role="button"], [class*="option"], [class*="mode"]');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.width > 0) {
                        const text = (el.innerText || '').trim();
                        if (text && text.length > 1 && text.length < 80 && !seen.has(text)) {
                            seen.add(text);
                            items.push({text, y: Math.round(rect.y), cls: (el.className || '').substring(0, 40)});
                        }
                    }
                }
                return items.sort((a, b) => a.y - b.y).slice(0, 20);
            }""")
            print("\n  Video modes/buttons:")
            for m in video_modes:
                print(f"    [{m['cls'][:20]}] {m['text']}")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 8. LIP SYNC — FULL =====
        print("\n" + "="*60)
        print("8. LIP SYNC DEEP DIVE")
        print("="*60)

        if click_sidebar_tool(page, "Lip Sync"):
            page.wait_for_timeout(1500)
            ss(page, "B12_lip_sync")

            # Detailed panel mapping
            lip_items = page.evaluate("""() => {
                const items = [];
                const seen = new Set();
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 850 &&
                        rect.width > 10 && rect.height > 5) {
                        const text = (el.innerText || '').trim();
                        const tag = el.tagName;
                        const cls = (el.className || '').toString().substring(0, 60);
                        const id = el.id || '';
                        if (text && text.length > 1 && text.length < 150 &&
                            el.children.length < 5 && !seen.has(text)) {
                            seen.add(text);
                            items.push({tag, cls, id, text: text.substring(0, 100), y: Math.round(rect.y)});
                        }
                    }
                }
                return items.sort((a, b) => a.y - b.y).slice(0, 30);
            }""")
            print("\n  Lip Sync full panel:")
            for item in lip_items:
                ident = item['id'] or item['cls'][:30]
                print(f"    y={item['y']} <{item['tag']}> [{ident}] {item['text'][:70]}")

            # Find all file inputs (for audio upload)
            file_inputs = page.evaluate("""() => {
                const items = [];
                const all = document.querySelectorAll('input[type="file"]');
                for (const el of all) {
                    items.push({
                        accept: el.accept || '',
                        id: el.id || '',
                        name: el.name || '',
                        cls: (el.className || '').toString().substring(0, 60),
                        display: getComputedStyle(el).display,
                    });
                }
                return items;
            }""")
            print(f"\n  File inputs: {len(file_inputs)}")
            for fi in file_inputs:
                print(f"    {fi}")

            # Check upload buttons
            upload_btns = page.evaluate("""() => {
                const items = [];
                const all = document.querySelectorAll('button, [role="button"]');
                for (const el of all) {
                    const text = (el.innerText || '').trim();
                    if ((text.includes('Upload') || text.includes('Pick') || text.includes('upload') ||
                         text.includes('Audio') || text.includes('audio') || text.includes('Face')) &&
                        text.length < 80) {
                        const rect = el.getBoundingClientRect();
                        items.push({
                            text,
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            cls: (el.className || '').toString().substring(0, 40),
                        });
                    }
                }
                return items;
            }""")
            print(f"\n  Upload/Pick buttons:")
            for btn in upload_btns:
                print(f"    ({btn['x']},{btn['y']}) [{btn['cls'][:20]}] {btn['text']}")

            # Check generation mode buttons
            mode_btns = page.evaluate("""() => {
                const items = [];
                const all = document.querySelectorAll('button, [role="button"], [class*="radio"], [class*="mode"]');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.width > 0) {
                        const text = (el.innerText || '').trim();
                        const active = el.classList.contains('active') || el.classList.contains('selected');
                        if (text && (text === 'Normal' || text === 'Pro' || text === '720p' || text === '1080p'
                                     || text.includes('Generate'))) {
                            items.push({text, active, cls: (el.className || '').substring(0, 40)});
                        }
                    }
                }
                return items;
            }""")
            print(f"\n  Mode buttons:")
            for mb in mode_btns:
                print(f"    [{mb['cls'][:20]}] {mb['text']} active={mb['active']}")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 9. VIDEO EDITOR =====
        print("\n" + "="*60)
        print("9. VIDEO EDITOR")
        print("="*60)

        if click_sidebar_tool(page, "Video Editor"):
            page.wait_for_timeout(1500)
            ss(page, "B13_video_editor")
            map_panel_items(page, "Video Editor")
            map_inputs(page, "Video Editor")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 10. MOTION CONTROL =====
        print("\n" + "="*60)
        print("10. MOTION CONTROL")
        print("="*60)

        if click_sidebar_tool(page, "Motion Control"):
            page.wait_for_timeout(1500)
            ss(page, "B14_motion_control")
            map_panel_items(page, "Motion Control")
            map_inputs(page, "Motion Control")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 11. ENHANCE & UPSCALE =====
        print("\n" + "="*60)
        print("11. ENHANCE & UPSCALE")
        print("="*60)

        # This tool is lower in sidebar, need scrollIntoView
        enhance_clicked = page.evaluate("""() => {
            const sidebar = document.querySelector('[class*="sidebar"], [class*="tool-list"]');
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.innerText || '').trim();
                if (text === 'Enhance &\\nUpscale' || text === 'Enhance & Upscale' || text === 'Enhance &\nUpscale') {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
            }
            // Try partial match
            for (const el of all) {
                const text = (el.innerText || '').trim();
                if (text.startsWith('Enhance') && el.getBoundingClientRect().x < 70) {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if enhance_clicked:
            page.wait_for_timeout(2000)
            ss(page, "B15_enhance")
            map_panel_items(page, "Enhance & Upscale")
            map_inputs(page, "Enhance & Upscale")
        else:
            print("  Enhance & Upscale not found in sidebar")
            # Try direct click
            if click_sidebar_tool(page, "Enhance"):
                page.wait_for_timeout(1500)
                ss(page, "B15_enhance")
                map_panel_items(page, "Enhance & Upscale")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 12. IMAGE EDITOR =====
        print("\n" + "="*60)
        print("12. IMAGE EDITOR")
        print("="*60)

        ie_clicked = page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.innerText || '').trim();
                if (text === 'Image Editor' && el.getBoundingClientRect().x < 70) {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if ie_clicked:
            page.wait_for_timeout(2000)
            ss(page, "B16_image_editor")
            map_panel_items(page, "Image Editor")
            map_inputs(page, "Image Editor")
        else:
            if click_sidebar_tool(page, "Image Editor"):
                ss(page, "B16_image_editor")
                map_panel_items(page, "Image Editor")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 13. INSTANT STORYBOARD =====
        print("\n" + "="*60)
        print("13. INSTANT STORYBOARD")
        print("="*60)

        sb_clicked = page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.innerText || '').trim();
                if ((text === 'Instant Storyboard' || text === 'Instant\\nStoryboard' || text === 'Instant\nStoryboard') && el.getBoundingClientRect().x < 70) {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if sb_clicked:
            page.wait_for_timeout(2000)
            ss(page, "B17_storyboard")
            map_panel_items(page, "Storyboard")
            map_inputs(page, "Storyboard")
        else:
            if click_sidebar_tool(page, "Instant"):
                ss(page, "B17_storyboard")
                map_panel_items(page, "Storyboard")

        close_left_panel(page)
        page.wait_for_timeout(500)

        # ===== 14. TOP BAR PROCESSING TOOLS =====
        print("\n" + "="*60)
        print("14. TOP BAR PROCESSING TOOLS")
        print("="*60)

        for tool_name in ["AI Eraser", "Hand Repair", "Expression", "BG Remove"]:
            print(f"\n  --- {tool_name} ---")
            tool_btn = page.locator(f'text="{tool_name}"')
            if tool_btn.count() > 0:
                try:
                    tool_btn.first.click(force=True, timeout=3000)
                    page.wait_for_timeout(1500)
                    ss(page, f"B18_{tool_name.replace(' ', '_').lower()}")

                    # Map the panel/dialog
                    tool_content = page.evaluate("""(toolName) => {
                        const items = [];
                        const seen = new Set();
                        const all = document.querySelectorAll('*');
                        for (const el of all) {
                            const rect = el.getBoundingClientRect();
                            if (rect.y > 60 && rect.y < 700 && rect.x > 60 && rect.x < 500 && rect.width > 20) {
                                const text = (el.innerText || '').trim();
                                if (text && text.length > 1 && text.length < 120 && el.children.length < 4 && !seen.has(text)) {
                                    seen.add(text);
                                    items.push({text: text.substring(0, 80), tag: el.tagName, y: Math.round(rect.y)});
                                }
                            }
                        }
                        return items.sort((a, b) => a.y - b.y).slice(0, 15);
                    }""", tool_name)
                    for t in tool_content:
                        print(f"    <{t['tag']}> {t['text']}")

                    # Close with Escape
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                except Exception as exc:
                    print(f"  {tool_name}: {exc}")
            else:
                print(f"  {tool_name}: not found")

        # ===== 15. TOP BAR ADDITIONAL ICONS =====
        print("\n" + "="*60)
        print("15. TOP BAR ICONS")
        print("="*60)

        top_icons = page.evaluate("""() => {
            const items = [];
            // Get all elements in the top toolbar area
            const all = document.querySelectorAll('button, [role="button"], a, [class*="icon"]');
            for (const el of all) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 60 && rect.y < 120 && rect.x > 400 && rect.width > 0 && rect.height > 0) {
                    const title = el.getAttribute('title') || '';
                    const cls = (el.className || '').toString().substring(0, 60);
                    const text = (el.innerText || '').trim().substring(0, 30);
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    items.push({title, class: cls, text, ariaLabel, x: Math.round(rect.x), y: Math.round(rect.y)});
                }
            }
            return items.sort((a, b) => a.x - b.x);
        }""")
        print(f"\n  Top bar icons ({len(top_icons)}):")
        for icon in top_icons:
            ident = icon['title'] or icon['ariaLabel'] or icon['text'] or icon['class'][:30]
            print(f"    @{icon['x']}px: {ident}")

        # ===== 16. CANVAS LAYERS PANEL =====
        print("\n" + "="*60)
        print("16. LAYERS PANEL")
        print("="*60)

        layers_tab = page.locator('.header-item.item-layers, text="Layers"')
        if layers_tab.count() > 0:
            layers_tab.first.click(force=True, timeout=3000)
            page.wait_for_timeout(1500)
            ss(page, "B19_layers")

            layers = page.evaluate("""() => {
                const items = [];
                const all = document.querySelectorAll('[class*="layer"] *');
                const seen = new Set();
                for (const el of all) {
                    const text = (el.innerText || '').trim();
                    const cls = (el.className || '').toString().substring(0, 40);
                    if (text && text.length > 1 && text.length < 80 && !seen.has(text)) {
                        seen.add(text);
                        items.push({text, cls});
                    }
                }
                return items.slice(0, 20);
            }""")
            print(f"\n  Layers panel:")
            for l in layers:
                print(f"    [{l['cls'][:20]}] {l['text']}")

        # Switch back to Results
        results_tab = page.locator('.header-item.item-result, text="Results"')
        if results_tab.count() > 0:
            results_tab.first.click(force=True, timeout=3000)
            page.wait_for_timeout(1000)

        # ===== 17. EXPORT BUTTON EXPLORATION =====
        print("\n" + "="*60)
        print("17. EXPORT")
        print("="*60)

        export_btn = page.locator('button.export, text="Export"')
        if export_btn.count() > 0:
            enabled = export_btn.first.evaluate("e => !e.disabled && !e.classList.contains('disabled')")
            print(f"  Export button enabled: {enabled}")
            if enabled:
                try:
                    export_btn.first.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    ss(page, "B20_export_dialog")

                    # Map export options
                    export_opts = page.evaluate("""() => {
                        const items = [];
                        const seen = new Set();
                        const all = document.querySelectorAll('[class*="export"] *, [class*="modal"] *, [class*="dialog"] *');
                        for (const el of all) {
                            const text = (el.innerText || '').trim();
                            if (text && text.length > 1 && text.length < 100 && !seen.has(text)) {
                                seen.add(text);
                                items.push(text);
                            }
                        }
                        return items.slice(0, 20);
                    }""")
                    for o in export_opts:
                        print(f"    {o}")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                except Exception as exc:
                    print(f"  Export error: {exc}")
            else:
                print("  Export disabled (no content on canvas)")

        # ===== 18. CANVAS SIZE / ASPECT RATIO CONTROLS =====
        print("\n" + "="*60)
        print("18. CANVAS SIZE CONTROLS")
        print("="*60)

        size_btn = page.locator('text="1536 × 1536"')
        if size_btn.count() == 0:
            # Try finding the size indicator in top bar
            size_btn = page.locator('[class*="canvas-size"], [class*="resolution"]')
        if size_btn.count() > 0:
            try:
                size_btn.first.click(timeout=3000)
                page.wait_for_timeout(2000)
                ss(page, "B21_canvas_size")

                # Map size options
                size_opts = page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.y > 0 && rect.y < 600 && rect.width > 20) {
                            const text = (el.innerText || '').trim();
                            if (text && (text.includes(':') || text.includes('×') || text.includes('Custom') || text.includes('Apply') || text.includes('Cancel'))
                                && text.length < 60 && !seen.has(text)) {
                                seen.add(text);
                                items.push(text);
                            }
                        }
                    }
                    return items.slice(0, 20);
                }""")
                print("\n  Size options:")
                for s in size_opts:
                    print(f"    {s}")

                # Cancel to not change anything
                cancel = page.locator('button:has-text("Cancel")')
                if cancel.count() > 0:
                    cancel.first.click(force=True, timeout=3000)
                    page.wait_for_timeout(500)
                else:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
            except Exception as exc:
                print(f"  Canvas size error: {exc}")

        print("\n\n" + "="*60)
        print("PHASE 8 COMPLETE — Canvas tools fully mapped")
        print("="*60)

    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        # Don't close the canvas page, we need it for next phases
        if should_close:
            context.close()
        pw.stop()


if __name__ == "__main__":
    main()
