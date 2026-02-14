"""Phase 7: Deep-dive every Dzine feature. Become an expert.

Explores: Img2Img controls, Advanced settings, Enhance, Image Editor,
Expression Edit, Face Swap, BG Remove, AI Eraser, existing Ray character,
Community styles, export formats, layer system.
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
            if btn.count() > 0 and btn.first.is_visible(timeout=2000):
                btn.first.click()
                page.wait_for_timeout(500)
                continue
        except Exception:
            pass
        break


def close_overlay(page):
    """Close any blocking overlay (result preview, size dialog, popup)."""
    close_popup(page)
    # Close result preview
    try:
        preview = page.locator('#result-preview')
        if preview.count() > 0 and preview.first.is_visible(timeout=1000):
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
    except Exception:
        pass
    # Close size dialog
    try:
        cancel = page.locator('button.cancel:has-text("Cancel")')
        if cancel.count() > 0 and cancel.first.is_visible(timeout=1000):
            cancel.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


def click_sidebar(page, text):
    """Click a sidebar tool, handling overlays."""
    close_overlay(page)
    page.locator(f'text="{text}"').first.click(force=True, timeout=5000)
    page.wait_for_timeout(2000)


def map_panel(page, label=""):
    """Map all visible panel content."""
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
                    items.push({text, y: Math.round(rect.y)});
                }
            }
        }
        return items.sort((a, b) => a.y - b.y).slice(0, 50);
    }""")
    print(f"\n  {label} panel ({len(items)} items):")
    for item in items:
        print(f"    {item['text']}")
    return items


def map_inputs(page, label=""):
    """Map all interactive elements in the current panel."""
    inputs = page.evaluate("""() => {
        const items = [];
        const panel = document.querySelector('.gen-config-form') || document.querySelector('.gen-config-body');
        const scope = panel || document;

        // Textareas
        for (const ta of scope.querySelectorAll('textarea')) {
            items.push({type: 'textarea', placeholder: ta.placeholder || '', maxLength: ta.maxLength || 0, visible: ta.offsetWidth > 0});
        }
        // Contenteditable
        for (const ce of scope.querySelectorAll('[contenteditable="true"]')) {
            items.push({type: 'contenteditable', placeholder: ce.getAttribute('data-placeholder') || '', visible: ce.offsetWidth > 0});
        }
        // Sliders / range
        for (const s of scope.querySelectorAll('input[type="range"], [role="slider"]')) {
            const label = s.getAttribute('aria-label') || s.closest('[class*="config"]')?.querySelector('label, .label, .title')?.innerText || '';
            items.push({type: 'slider', label, value: s.value || '', min: s.min || '', max: s.max || ''});
        }
        // Toggles
        for (const t of scope.querySelectorAll('[role="switch"], .switch, [class*="toggle"]')) {
            const label = t.closest('[class*="config"]')?.querySelector('.label, .title')?.innerText || t.previousElementSibling?.innerText || '';
            const checked = t.classList.contains('active') || t.getAttribute('aria-checked') === 'true';
            items.push({type: 'toggle', label: label.substring(0, 40), checked});
        }
        // Dropdowns
        for (const d of scope.querySelectorAll('select, [class*="select"], [class*="dropdown"]')) {
            const text = (d.innerText || '').trim().substring(0, 60);
            if (text) items.push({type: 'dropdown', text});
        }
        // File inputs
        for (const f of scope.querySelectorAll('input[type="file"]')) {
            items.push({type: 'file', accept: f.accept || ''});
        }
        // Number inputs
        for (const n of scope.querySelectorAll('input[type="number"]')) {
            items.push({type: 'number', value: n.value || '', placeholder: n.placeholder || ''});
        }
        return items;
    }""")
    if inputs:
        print(f"\n  {label} inputs:")
        for inp in inputs:
            print(f"    {inp}")
    return inputs


def wait_result(page, initial=0, max_s=120):
    start = time.monotonic()
    while time.monotonic() - start < max_s:
        page.wait_for_timeout(3000)
        imgs = page.locator('.result-panel img, .material-v2-result-content img, .result-item img')
        if imgs.count() > initial:
            print(f"  Result after {time.monotonic()-start:.0f}s ({imgs.count()} imgs)")
            return True
        if int(time.monotonic()-start) % 15 == 0 and int(time.monotonic()-start) > 0:
            print(f"  ... {time.monotonic()-start:.0f}s")
    return False


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    # Clean up tabs
    print(f"\n  Tabs: {len(context.pages)}")
    seen = set()
    for p in list(context.pages):
        u = p.url
        if u in seen or ("canvas" in u and "19797967" not in u):
            print(f"    Closing: {u[:60]}")
            p.close()
        else:
            seen.add(u)
    print(f"  Remaining: {len(context.pages)}")

    page = context.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    try:
        # ===== 1. OPEN EXISTING PROJECT (with Ray) =====
        print("\n===== 1. EXISTING PROJECT WITH RAY =====")
        page.goto("https://www.dzine.ai/projects", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        close_popup(page)
        ss(page, "A01_projects")

        # List all projects
        projects = page.evaluate("""() => {
            const items = [];
            const btns = document.querySelectorAll('button.project-item');
            for (const b of btns) {
                items.push({id: b.id, text: (b.innerText || '').trim().substring(0, 80)});
            }
            return items;
        }""")
        print(f"  Projects ({len(projects)}):")
        for p in projects:
            print(f"    id={p['id']} {p['text']}")

        # Open the first project that has content (has "Items" in text)
        target = None
        for p in projects:
            if "Items" in p["text"] or "item" in p["text"].lower():
                target = p
                break
        if not target and projects:
            target = projects[0]

        if target:
            print(f"\n  Opening project: {target['id']}")
            page.locator(f"#\\3{target['id'][0]} {target['id'][1:]}").first.dblclick(force=True, timeout=5000)
            page.wait_for_timeout(5000)
            close_overlay(page)
            print(f"  URL: {page.url}")
            ss(page, "A02_project_open")

        # ===== 2. EXPLORE CHARACTER TOOL — MANAGE CHARACTERS =====
        print("\n===== 2. CHARACTER — MANAGE =====")
        click_sidebar(page, "Character")
        ss(page, "A03_character")

        # Click "Manage Your Characters"
        manage_btn = page.locator('text="Manage Your Characters"')
        if manage_btn.count() > 0:
            manage_btn.first.click(force=True, timeout=5000)
            page.wait_for_timeout(3000)
            ss(page, "A04_manage_characters")

            # Map characters
            chars = page.evaluate("""() => {
                const items = [];
                const all = document.querySelectorAll('[class*="character"] img, [class*="char-item"] img, [class*="character-card"] img');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0) {
                        const alt = el.alt || '';
                        const src = (el.src || '').substring(0, 100);
                        items.push({alt, src, w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
                return items;
            }""")
            print(f"  Characters found: {len(chars)}")
            for c in chars:
                print(f"    {c['alt']!r} {c['w']}x{c['h']}")

            # Also get character names via text
            char_names = page.evaluate("""() => {
                const items = [];
                const seen = new Set();
                const all = document.querySelectorAll('[class*="character"] *, [class*="char"] *');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const text = (el.innerText || '').trim();
                        if (text && text.length > 1 && text.length < 50 && el.children.length < 2 && !seen.has(text)) {
                            seen.add(text);
                            items.push(text);
                        }
                    }
                }
                return items;
            }""")
            print(f"  Character names/labels:")
            for n in char_names:
                print(f"    - {n}")

        # Go back to Character main
        try:
            page.go_back()
            page.wait_for_timeout(2000)
        except Exception:
            pass

        # ===== 3. CHARACTER — BUILD (explore the builder) =====
        print("\n===== 3. CHARACTER — BUILD =====")
        click_sidebar(page, "Character")
        build_btn = page.locator('text="Build Your Character"')
        if build_btn.count() > 0:
            build_btn.first.click(force=True, timeout=5000)
            page.wait_for_timeout(3000)
            ss(page, "A05_build_character")
            map_panel(page, "Build Character")
            map_inputs(page, "Build Character")

            # Go back
            try:
                back_btn = page.locator('button:has-text("Back"), [class*="back"]')
                if back_btn.count() > 0:
                    back_btn.first.click(force=True, timeout=3000)
                    page.wait_for_timeout(1000)
            except Exception:
                pass

        # ===== 4. CHARACTER — GENERATE IMAGES =====
        print("\n===== 4. CHARACTER — GENERATE IMAGES =====")
        click_sidebar(page, "Character")
        gen_imgs_btn = page.locator('text="Generate Images"')
        if gen_imgs_btn.count() > 0:
            gen_imgs_btn.first.click(force=True, timeout=5000)
            page.wait_for_timeout(3000)
            ss(page, "A06_generate_with_char")
            map_panel(page, "Generate with Character")
            map_inputs(page, "Generate with Character")

        # ===== 5. CHARACTER — INSERT CHARACTER =====
        print("\n===== 5. CHARACTER — INSERT =====")
        click_sidebar(page, "Character")
        insert_btn = page.locator('text="Insert Character"')
        if insert_btn.count() > 0:
            insert_btn.first.click(force=True, timeout=5000)
            page.wait_for_timeout(3000)
            ss(page, "A07_insert_character")
            map_panel(page, "Insert Character")

        # ===== 6. CHARACTER — CHARACTER SHEET =====
        print("\n===== 6. CHARACTER — SHEET =====")
        click_sidebar(page, "Character")
        sheet_btn = page.locator('text="Character Sheet"')
        if sheet_btn.count() > 0:
            sheet_btn.first.click(force=True, timeout=5000)
            page.wait_for_timeout(3000)
            ss(page, "A08_character_sheet")
            map_panel(page, "Character Sheet")

        # ===== 7. Img2Img IN DEPTH =====
        print("\n===== 7. Img2Img DEEP DIVE =====")
        click_sidebar(page, "Img2Img")
        ss(page, "A09_img2img")
        map_panel(page, "Img2Img")
        map_inputs(page, "Img2Img")

        # Click on style selector for Img2Img
        style_btn = page.locator('.c-style button.style, .c-style .content')
        if style_btn.count() > 0:
            try:
                style_btn.first.click(force=True, timeout=5000)
                page.wait_for_timeout(2000)
                ss(page, "A10_img2img_styles")
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

        # Click Advanced in Img2Img
        adv = page.locator('text="Advanced"')
        if adv.count() > 0:
            try:
                adv.first.click(force=True, timeout=5000)
                page.wait_for_timeout(1500)
                ss(page, "A11_img2img_advanced")
                map_panel(page, "Img2Img Advanced")
            except Exception:
                pass

        # ===== 8. Txt2Img ADVANCED SETTINGS =====
        print("\n===== 8. Txt2Img ADVANCED =====")
        click_sidebar(page, "Txt2Img")
        page.wait_for_timeout(1000)

        adv2 = page.locator('.gen-config-params text="Advanced", .gen-config-form text="Advanced"')
        if adv2.count() > 0:
            try:
                adv2.first.click(force=True, timeout=5000)
                page.wait_for_timeout(1500)
                ss(page, "A12_txt2img_advanced")
                map_panel(page, "Txt2Img Advanced")
                map_inputs(page, "Txt2Img Advanced")
            except Exception:
                pass

        # ===== 9. AI VIDEO =====
        print("\n===== 9. AI VIDEO =====")
        click_sidebar(page, "AI Video")
        ss(page, "A13_ai_video")
        map_panel(page, "AI Video")
        map_inputs(page, "AI Video")

        # ===== 10. LIP SYNC — FULL EXPLORATION =====
        print("\n===== 10. LIP SYNC DEEP =====")
        click_sidebar(page, "Lip Sync")
        ss(page, "A14_lip_sync")

        # Map the full Lip Sync panel content
        lip_full = page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 60 && rect.x < 400 && rect.y > 50 && rect.y < 800 && rect.width > 10) {
                    const text = (el.innerText || '').trim();
                    const tag = el.tagName;
                    const cls = (el.className || '').toString().substring(0, 60);
                    if (text && text.length < 150 && el.children.length < 5 && !seen.has(text)) {
                        seen.add(text);
                        items.push({tag, class: cls, text, y: Math.round(rect.y)});
                    }
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 30);
        }""")
        print("\n  Lip Sync full panel:")
        for item in lip_full:
            print(f"    <{item['tag']}> class={item['class']!r} text={item['text']!r}")

        # Check for audio upload input
        lip_audio = page.evaluate("""() => {
            const items = [];
            const all = document.querySelectorAll('input[type="file"], [class*="upload"], [class*="audio"]');
            for (const el of all) {
                const rect = el.getBoundingClientRect();
                items.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    accept: el.accept || '',
                    type: el.type || '',
                    visible: rect.width > 0,
                    x: Math.round(rect.x), y: Math.round(rect.y),
                });
            }
            return items;
        }""")
        print("\n  Audio/file inputs:")
        for item in lip_audio:
            print(f"    {item}")

        # ===== 11. VIDEO EDITOR =====
        print("\n===== 11. VIDEO EDITOR =====")
        click_sidebar(page, "Video Editor")
        ss(page, "A15_video_editor")
        map_panel(page, "Video Editor")

        # ===== 12. MOTION CONTROL =====
        print("\n===== 12. MOTION CONTROL =====")
        click_sidebar(page, "Motion Control")
        ss(page, "A16_motion_control")
        map_panel(page, "Motion Control")

        # ===== 13. ENHANCE & UPSCALE =====
        print("\n===== 13. ENHANCE & UPSCALE =====")
        # This one is lower in sidebar, need to scroll or use JS click
        enhance = page.locator('text="Enhance"')
        if enhance.count() > 0:
            try:
                enhance.first.evaluate("e => e.scrollIntoView()")
                page.wait_for_timeout(500)
                enhance.first.click(force=True, timeout=5000)
                page.wait_for_timeout(2000)
                ss(page, "A17_enhance")
                map_panel(page, "Enhance")
                map_inputs(page, "Enhance")
            except Exception as exc:
                print(f"  Enhance click error: {exc}")
                # Try clicking by position
                try:
                    enhance.first.evaluate("e => e.click()")
                    page.wait_for_timeout(2000)
                    ss(page, "A17_enhance")
                    map_panel(page, "Enhance")
                except Exception:
                    pass

        # ===== 14. IMAGE EDITOR =====
        print("\n===== 14. IMAGE EDITOR =====")
        ie_btn = page.locator('text="Image Editor"')
        if ie_btn.count() > 0:
            try:
                ie_btn.first.evaluate("e => e.scrollIntoView()")
                page.wait_for_timeout(500)
                ie_btn.first.click(force=True, timeout=5000)
                page.wait_for_timeout(2000)
                ss(page, "A18_image_editor")
                map_panel(page, "Image Editor")
                map_inputs(page, "Image Editor")
            except Exception as exc:
                print(f"  Image Editor error: {exc}")

        # ===== 15. INSTANT STORYBOARD =====
        print("\n===== 15. INSTANT STORYBOARD =====")
        sb_btn = page.locator('text="Instant"')
        if sb_btn.count() > 0:
            try:
                sb_btn.first.evaluate("e => e.scrollIntoView()")
                page.wait_for_timeout(500)
                sb_btn.first.click(force=True, timeout=5000)
                page.wait_for_timeout(2000)
                ss(page, "A19_storyboard")
                map_panel(page, "Storyboard")
            except Exception:
                pass

        # ===== 16. TOP BAR PROCESSING TOOLS =====
        print("\n===== 16. TOP PROCESSING TOOLS =====")

        # Click AI Eraser
        for tool_name in ["AI Eraser", "Hand Repair", "Expression", "BG Remove"]:
            tool_btn = page.locator(f'text="{tool_name}"')
            if tool_btn.count() > 0:
                try:
                    tool_btn.first.click(force=True, timeout=3000)
                    page.wait_for_timeout(1500)
                    ss(page, f"A20_{tool_name.replace(' ', '_').lower()}")

                    # Map whatever panel/dialog appeared
                    tool_content = page.evaluate("""() => {
                        const items = [];
                        const seen = new Set();
                        const all = document.querySelectorAll('*');
                        for (const el of all) {
                            const rect = el.getBoundingClientRect();
                            if (rect.y > 80 && rect.y < 600 && rect.x > 60 && rect.x < 500 && rect.width > 20) {
                                const text = (el.innerText || '').trim();
                                if (text && text.length < 100 && el.children.length < 4 && !seen.has(text)) {
                                    seen.add(text);
                                    items.push(text);
                                }
                            }
                        }
                        return items.slice(0, 15);
                    }""")
                    print(f"\n  {tool_name}:")
                    for t in tool_content:
                        print(f"    {t}")
                except Exception as exc:
                    print(f"  {tool_name}: {exc}")

        # ===== 17. TOP BAR ADDITIONAL ICONS =====
        print("\n===== 17. TOP ICONS (crop, perspective, etc.) =====")
        top_icons = page.evaluate("""() => {
            const items = [];
            const all = document.querySelectorAll('button, [role="button"]');
            for (const el of all) {
                const rect = el.getBoundingClientRect();
                if (rect.y > 70 && rect.y < 120 && rect.x > 700 && rect.width > 0 && rect.width < 60) {
                    const title = el.getAttribute('title') || '';
                    const cls = (el.className || '').toString().substring(0, 60);
                    const text = (el.innerText || '').trim().substring(0, 30);
                    items.push({title, class: cls, text, x: Math.round(rect.x)});
                }
            }
            return items.sort((a, b) => a.x - b.x);
        }""")
        for icon in top_icons:
            ident = icon['title'] or icon['text'] or icon['class'][:30]
            print(f"    @{icon['x']}px: {ident}")

        # ===== 18. COMMUNITY STYLES IN DEPTH =====
        print("\n===== 18. COMMUNITY STYLES =====")
        page.goto("https://www.dzine.ai/community/list/all", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        close_popup(page)
        ss(page, "A21_community")

        community_items = page.evaluate("""() => {
            const items = [];
            const cards = document.querySelectorAll('[class*="card"], [class*="item"], [class*="post"]');
            for (const c of cards) {
                const rect = c.getBoundingClientRect();
                if (rect.width > 100 && rect.height > 100) {
                    const text = (c.innerText || '').trim().substring(0, 100);
                    if (text && text.length > 3) items.push(text);
                }
            }
            return [...new Set(items)].slice(0, 15);
        }""")
        for item in community_items:
            print(f"    {item}")

        # ===== 19. ASSET LIBRARY =====
        print("\n===== 19. ASSET LIBRARY =====")
        page.goto("https://www.dzine.ai/asset", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        close_popup(page)
        ss(page, "A22_assets")

        # Check tabs
        print("\n  Asset tabs:")
        tabs = page.locator('[class*="tab"], [role="tab"]')
        for i in range(tabs.count()):
            try:
                text = tabs.nth(i).evaluate("e => e.innerText") or ""
                visible = tabs.nth(i).is_visible()
                if visible and text.strip():
                    print(f"    {text.strip()}")
            except Exception:
                pass

        # Click "All Results" tab
        results_tab = page.locator('text="All Results"')
        if results_tab.count() > 0:
            results_tab.first.click(force=True, timeout=5000)
            page.wait_for_timeout(2000)
            ss(page, "A23_all_results")

            # Count results
            result_items = page.locator('[class*="result"] img, [class*="asset"] img')
            print(f"  All Results images: {result_items.count()}")

        # ===== 20. API PAGE — DOCUMENTATION LINKS =====
        print("\n===== 20. API DOCS =====")
        page.goto("https://www.dzine.ai/api/", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        close_popup(page)

        # Find "API Documentation" link
        api_doc_link = page.locator('a:has-text("API Documentation"), a:has-text("Documentation")')
        if api_doc_link.count() > 0:
            href = api_doc_link.first.evaluate("e => e.href") or ""
            print(f"  API Docs link: {href}")
            if href:
                api_doc_link.first.click(timeout=5000)
                page.wait_for_timeout(3000)
                close_popup(page)
                ss(page, "A24_api_docs")
                print(f"  API Docs URL: {page.url}")

                # Get the API documentation structure
                api_structure = page.evaluate("""() => {
                    const headings = [];
                    const all = document.querySelectorAll('h1, h2, h3, h4');
                    for (const h of all) {
                        const text = (h.innerText || '').trim();
                        if (text) headings.push({level: h.tagName, text: text.substring(0, 80)});
                    }
                    return headings.slice(0, 30);
                }""")
                for h in api_structure:
                    print(f"    {h['level']}: {h['text']}")

        # ===== 21. PRICING DETAILS =====
        print("\n===== 21. PRICING =====")
        page.goto("https://www.dzine.ai/pricing/", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        close_popup(page)
        ss(page, "A25_pricing")

        pricing = page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            const all = document.querySelectorAll('[class*="plan"] *, [class*="pricing"] *, [class*="tier"] *');
            for (const el of all) {
                const text = (el.innerText || '').trim();
                if (text && text.length > 2 && text.length < 200 && el.children.length < 3 && !seen.has(text)) {
                    seen.add(text);
                    items.push(text);
                }
            }
            return items.slice(0, 40);
        }""")
        for p in pricing:
            print(f"    {p}")

        print("\n\n===== PHASE 7 COMPLETE =====")

    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        page.close()
        if should_close:
            context.close()
        pw.stop()


if __name__ == "__main__":
    main()
