#!/usr/bin/env python3
"""Dzine Deep Exploration Part 21 — Close Blocking Dialog + 4K NBP Generation + Img2Img.

PRIORITY: Close Pick Image dialog first, then test real workflows.

1. Close Pick Image dialog (blocking all sidebar navigation)
2. Map sidebar icons precisely (get exact y-coordinates)
3. Open Txt2Img → NBP → 4K → 16:9 → generate product image
4. Open Img2Img → upload product image from artifacts → generate variation
5. Map all sidebar tools with their y-positions
"""

import json
import sys
import time
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def close_all_dialogs(page):
    """Aggressively close ALL dialogs, popups, overlays."""
    # 1. Close Pick Image dialog specifically
    page.evaluate("""() => {
        // Pick Image dialog close
        var pick = document.querySelector('.pick-image-dialog');
        if (pick) {
            var close = pick.querySelector('.ico-close, [class*="close"], button.close');
            if (close) { close.click(); return 'pick-image-closed'; }
        }
        return 'no-pick-dialog';
    }""")
    page.wait_for_timeout(500)

    # 2. Close any X buttons on visible popups
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.ico-close, [class*="close-btn"], [class*="close-icon"]')) {
            if (el.offsetHeight > 0 && el.offsetWidth > 0) {
                try { el.click(); } catch(e) {}
            }
        }
    }""")
    page.wait_for_timeout(300)

    # 3. Close common dialog buttons
    page.evaluate("""() => {
        for (var text of ['Not now', 'Close', 'Never show again', 'Got it', 'Skip', 'Later', 'Cancel']) {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === text && btn.offsetHeight > 0) {
                    try { btn.click(); } catch(e) {}
                }
            }
        }
    }""")
    page.wait_for_timeout(300)

    # 4. Escape key (twice)
    page.keyboard.press('Escape')
    page.wait_for_timeout(400)
    page.keyboard.press('Escape')
    page.wait_for_timeout(400)

    # 5. Close any gen-config panels
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
    }""")
    page.wait_for_timeout(300)


def get_active_panel(page):
    """Return which panel/tool is currently active."""
    return page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        var text = (panel.innerText || '').substring(0, 80).trim();
        if (text.startsWith('Text to Image')) return 'txt2img';
        if (text.startsWith('AI Video')) return 'ai_video';
        if (text.startsWith('Enhance & Upscale')) return 'enhance';
        if (text.startsWith('Motion Control')) return 'motion';
        if (text.startsWith('Face Swap')) return 'face_swap';
        if (text.includes('Img2Img') || text.includes('Image to Image')) return 'img2img';
        return 'unknown:' + text.substring(0, 40);
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 21")
    print("Close Dialog + 4K NBP Generation + Img2Img")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")
    print(f"  Tabs: {len(context.pages)}")

    if "dzine.ai/canvas" not in page.url:
        print("  Navigating to canvas...")
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # STEP 0: Check current state and close everything
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 0: Diagnose and Close Blocking Dialogs")
    print("=" * 70)

    # Check what's blocking
    state = page.evaluate("""() => {
        var result = {};
        // Pick Image dialog?
        var pick = document.querySelector('.pick-image-dialog');
        result.pickImageVisible = pick ? (pick.offsetHeight > 0) : false;
        // Sound Effects?
        var sfx = document.querySelector('.sound-effects-popup');
        result.soundEffectsVisible = sfx ? (sfx.offsetHeight > 0) : false;
        // Any overlay/modal?
        var overlays = document.querySelectorAll('[class*="overlay"], [class*="modal"], [class*="dialog"], [class*="popup"]');
        result.overlays = [];
        for (var o of overlays) {
            if (o.offsetHeight > 0 && o.offsetWidth > 0) {
                var cls = (typeof o.className === 'string') ? o.className : '';
                result.overlays.push(cls.substring(0, 60));
            }
        }
        // Active panel?
        var panel = document.querySelector('.c-gen-config.show');
        result.activePanel = panel ? (panel.innerText || '').substring(0, 50).trim() : 'none';
        return result;
    }""")
    print(f"  Pick Image visible: {state.get('pickImageVisible')}")
    print(f"  Sound Effects visible: {state.get('soundEffectsVisible')}")
    print(f"  Active panel: {state.get('activePanel')}")
    print(f"  Visible overlays ({len(state.get('overlays', []))}):")
    for o in state.get('overlays', []):
        print(f"    > {o}")

    screenshot(page, "p211_before_cleanup")

    # Close everything
    close_all_dialogs(page)
    print("  Dialogs closed.")

    # Verify clean state
    panel = get_active_panel(page)
    print(f"  Panel after cleanup: {panel}")

    # Check again for overlays
    remaining = page.evaluate("""() => {
        var overlays = document.querySelectorAll('[class*="overlay"], [class*="modal"], [class*="dialog"], [class*="popup"]');
        var visible = [];
        for (var o of overlays) {
            if (o.offsetHeight > 0 && o.offsetWidth > 0) {
                var cls = (typeof o.className === 'string') ? o.className : '';
                visible.push(cls.substring(0, 60));
            }
        }
        return visible;
    }""")
    if remaining:
        print(f"  WARNING: Still visible overlays: {remaining}")
        # Try clicking the canvas area to dismiss
        page.mouse.click(700, 400)
        page.wait_for_timeout(500)
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)

    screenshot(page, "p211_after_cleanup")

    # ================================================================
    # STEP 1: Map sidebar icons precisely
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 1: Map Sidebar Icons (exact positions)")
    print("=" * 70)

    sidebar = page.evaluate("""() => {
        // The sidebar is the left-most column with tool icons
        var sidebar = document.querySelector('.c-side-tools, .sidebar, [class*="side-tool"]');
        if (!sidebar) {
            // Try to find it by position - leftmost column of icons
            var all = document.querySelectorAll('[class*="tool-item"], [class*="sidebar-item"]');
            if (all.length > 0) {
                return {found: 'by-items', count: all.length};
            }
        }

        // Map all clickable elements in the left 80px strip
        var items = [];
        var allElements = document.querySelectorAll('*');
        for (var el of allElements) {
            var rect = el.getBoundingClientRect();
            if (rect.x >= 0 && rect.x < 80 && rect.y > 50 && rect.y < 600
                && rect.width > 20 && rect.width < 70
                && rect.height > 20 && rect.height < 70
                && el.offsetHeight > 0) {
                var text = (el.getAttribute('title') || el.getAttribute('aria-label') ||
                           el.getAttribute('data-tooltip') || '').trim();
                // Also check for tooltip text
                if (!text) {
                    var inner = (el.innerText || '').trim();
                    if (inner.length < 20) text = inner;
                }
                var cls = (typeof el.className === 'string') ? el.className : '';
                var tag = el.tagName.toLowerCase();
                // Skip if parent already captured
                items.push({
                    tag: tag,
                    cls: cls.substring(0, 50),
                    x: Math.round(rect.x + rect.width / 2),
                    y: Math.round(rect.y + rect.height / 2),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                    text: text
                });
            }
        }
        return {items: items};
    }""")

    items = sidebar.get('items', [])
    print(f"  Found {len(items)} elements in sidebar strip (x < 80)")

    # Deduplicate by y-position (within 5px)
    unique = []
    seen_y = set()
    for item in sorted(items, key=lambda i: i['y']):
        y_bucket = round(item['y'] / 10) * 10
        key = f"{y_bucket}"
        if key not in seen_y:
            seen_y.add(key)
            unique.append(item)

    print(f"  Unique by y-position: {len(unique)}")
    for u in unique:
        text = u.get('text', '')
        cls = u.get('cls', '')
        print(f"    y={u['y']:3d}  x={u['x']:2d}  {u['w']}x{u['h']}  tag={u['tag']}  text='{text}'  cls={cls[:30]}")

    # ================================================================
    # STEP 2: Identify each sidebar icon by hovering
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 2: Identify sidebar icons by tooltip/hover")
    print("=" * 70)

    # Hover over each unique y-position and check for tooltips
    icon_map = {}
    for u in unique:
        if u['y'] < 80 or u['y'] > 550:
            continue
        page.mouse.move(u['x'], u['y'])
        page.wait_for_timeout(800)

        tooltip = page.evaluate("""() => {
            var tips = document.querySelectorAll('[class*="tooltip"], [class*="tip"], [role="tooltip"]');
            for (var t of tips) {
                if (t.offsetHeight > 0 && t.offsetWidth > 0) {
                    return (t.innerText || t.textContent || '').trim();
                }
            }
            return '';
        }""")
        if tooltip:
            icon_map[u['y']] = tooltip
            print(f"    y={u['y']}: {tooltip}")

    # Move mouse away
    page.mouse.move(400, 400)
    page.wait_for_timeout(300)

    # If tooltips didn't work, try clicking each and checking panel
    if len(icon_map) < 3:
        print("  Tooltips sparse, identifying by click + panel check...")
        for u in unique:
            if u['y'] < 80 or u['y'] > 550:
                continue
            page.mouse.click(u['x'], u['y'])
            page.wait_for_timeout(1500)
            panel = get_active_panel(page)
            if panel != 'none':
                icon_map[u['y']] = panel
                print(f"    y={u['y']}: opens -> {panel}")
                # Close panel
                page.keyboard.press('Escape')
                page.wait_for_timeout(500)

    print(f"\n  Sidebar icon map ({len(icon_map)} found):")
    for y, name in sorted(icon_map.items()):
        print(f"    y={y}: {name}")

    # ================================================================
    # STEP 3: Open Txt2Img and configure for 4K NBP
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 3: Txt2Img → NBP → 4K → 16:9 → Generate")
    print("=" * 70)

    # Find Txt2Img y-position from our map
    txt2img_y = None
    for y, name in icon_map.items():
        if 'txt2img' in name.lower() or 'text' in name.lower():
            txt2img_y = y
            break

    if not txt2img_y:
        # Default position from previous explorations
        txt2img_y = 190
        print(f"  Using default y={txt2img_y} for Txt2Img")

    page.mouse.click(40, txt2img_y)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel after Txt2Img click: {panel}")

    if panel == 'none':
        # Try clicking the sidebar icons from a slightly different approach
        print("  Panel didn't open. Trying direct sidebar icon click...")
        # Try finding the icon by its SVG or image content
        txt2img_clicked = page.evaluate("""() => {
            // Look for sidebar items with specific identifiers
            var items = document.querySelectorAll('[class*="tool-item"], [class*="menu-item"], .sidebar-icon');
            for (var item of items) {
                var text = (item.getAttribute('title') || item.getAttribute('data-tip') ||
                           item.innerText || '').toLowerCase();
                if (text.includes('text') && text.includes('image')) {
                    item.click();
                    return 'clicked: ' + text;
                }
            }
            // Try finding by the actual sidebar container
            var sidebar = document.querySelector('.c-side-tools');
            if (sidebar) {
                var children = sidebar.children;
                if (children.length > 0) {
                    // First tool is usually Txt2Img
                    children[0].click();
                    return 'clicked first sidebar child';
                }
            }
            return 'not found';
        }""")
        print(f"  Direct click result: {txt2img_clicked}")
        page.wait_for_timeout(2500)
        panel = get_active_panel(page)
        print(f"  Panel after direct click: {panel}")

    if panel == 'txt2img' or panel.startswith('unknown:Text'):
        # Check current model
        model = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'NO PANEL';
            var sn = panel.querySelector('.style-name');
            return sn ? (sn.innerText || '').trim() : 'unknown';
        }""")
        print(f"  Current model: {model}")

        # Select Nano Banana Pro if not already
        if model != 'Nano Banana Pro':
            print("  Selecting Nano Banana Pro...")
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                var btn = panel.querySelector('button.style, .style-btn, [class*="style-select"]');
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(2000)

            # Find and click NBP in the style picker
            nbp_clicked = page.evaluate("""() => {
                var picker = document.querySelector('.style-list-panel, [class*="style-list"]');
                if (!picker) return 'no picker';
                var items = picker.querySelectorAll('[class*="style-item"], .model-item, div');
                for (var item of items) {
                    var text = (item.innerText || '').trim();
                    if (text.includes('Nano Banana Pro')) {
                        item.click();
                        return 'clicked: ' + text.substring(0, 30);
                    }
                }
                // Also try by image alt/title
                for (var img of picker.querySelectorAll('img')) {
                    var alt = (img.alt || img.title || '').toLowerCase();
                    if (alt.includes('nano banana pro') || alt.includes('nbp')) {
                        img.click();
                        return 'clicked img: ' + alt;
                    }
                }
                return 'NBP not found in picker';
            }""")
            print(f"  NBP selection: {nbp_clicked}")
            page.wait_for_timeout(1000)
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

        # Select 4K quality
        print("  Selecting 4K quality...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            for (var btn of panel.querySelectorAll('button, [class*="option"]')) {
                var text = (btn.innerText || '').trim();
                if (text === '4K') { btn.click(); return; }
            }
        }""")
        page.wait_for_timeout(300)

        # Select 16:9 aspect ratio
        print("  Selecting 16:9 aspect ratio...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            // Look in aspect ratio container
            var ratioContainer = panel.querySelector('.c-aspect-ratio, [class*="aspect"], [class*="ratio"]');
            if (ratioContainer) {
                for (var item of ratioContainer.querySelectorAll('.item, div, span')) {
                    if ((item.innerText || '').trim() === '16:9') {
                        item.click();
                        return;
                    }
                }
            }
            // Fallback: search all elements
            for (var el of panel.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === '16:9' && el.offsetHeight > 0 && el.offsetHeight < 40) {
                    el.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(300)

        # Verify settings
        settings = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var sn = panel.querySelector('.style-name');
            var model = sn ? (sn.innerText || '').trim() : 'unknown';
            var quality = '';
            for (var btn of panel.querySelectorAll('button.selected, [class*="selected"], button.active, [class*="active"]')) {
                var t = (btn.innerText || '').trim();
                if (['1K', '2K', '4K'].includes(t)) quality = t;
            }
            var dims = '';
            var text = panel.innerText || '';
            var match = text.match(/(\\d+)\\s*[x×]\\s*(\\d+)/);
            if (match) dims = match[0];
            return {model: model, quality: quality, dims: dims};
        }""")
        print(f"  Settings: {json.dumps(settings)}")

        # Enter a product photography prompt
        prompt = "Professional product photography of premium wireless noise-cancelling headphones, matte black finish with silver accents, isolated on pure white background, studio lighting with soft diffusion, extremely detailed texture and material rendering, 8K commercial product shot, clean soft shadows, photorealistic, Amazon product listing style"
        page.evaluate("""(p) => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var ta = panel.querySelector('textarea');
            if (ta) {
                ta.focus();
                ta.value = p;
                ta.dispatchEvent(new Event('input', {bubbles: true}));
            }
        }""", prompt)
        page.wait_for_timeout(300)

        screenshot(page, "p211_txt2img_4k_setup")

        # SAFETY CHECK: Verify panel is still Txt2Img
        safety_check = get_active_panel(page)
        print(f"  Safety check — panel: {safety_check}")

        if safety_check == 'txt2img' or safety_check.startswith('unknown:Text'):
            # Check generate button text (should show credit cost)
            gen_info = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {found: false};
                var btn = panel.querySelector('.generative, #txt2img-generate-btn, button.generate');
                if (!btn) {
                    // Search for Generate button
                    for (var b of panel.querySelectorAll('button')) {
                        if ((b.innerText || '').includes('Generate')) {
                            return {found: true, text: (b.innerText || '').trim(), disabled: b.disabled};
                        }
                    }
                    return {found: false};
                }
                return {found: true, text: (btn.innerText || '').trim(), disabled: btn.disabled};
            }""")
            print(f"  Generate button: {json.dumps(gen_info)}")

            if gen_info.get('found') and not gen_info.get('disabled'):
                # Click Generate
                page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return;
                    var btn = panel.querySelector('.generative, #txt2img-generate-btn');
                    if (!btn) {
                        for (var b of panel.querySelectorAll('button')) {
                            if ((b.innerText || '').includes('Generate') && !b.disabled) {
                                b.click(); return;
                            }
                        }
                    } else if (!btn.disabled) {
                        btn.click();
                    }
                }""")
                print("  Generate clicked! Waiting for 4K NBP generation (90s max)...")

                # Wait and check progress periodically
                for i in range(6):
                    page.wait_for_timeout(15000)
                    progress = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return 'no panel';
                        var prog = panel.querySelector('[class*="progress"], [class*="loading"]');
                        if (prog && prog.offsetHeight > 0) return 'generating...';
                        // Check if result appeared
                        var results = document.querySelectorAll('[class*="result-item"]');
                        return 'results: ' + results.length;
                    }""")
                    elapsed = (i + 1) * 15
                    print(f"    [{elapsed}s] {progress}")

                screenshot(page, "p211_4k_nbp_result")
                print("  4K NBP generation complete!")
            else:
                print("  Generate button not ready")
                screenshot(page, "p211_txt2img_no_generate")
        else:
            print(f"  WRONG PANEL ({safety_check}) — skipping Generate")
    else:
        print(f"  Could not open Txt2Img panel (got: {panel})")
        screenshot(page, "p211_no_txt2img")

    # ================================================================
    # STEP 4: Img2Img workflow
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 4: Img2Img Workflow")
    print("=" * 70)

    # Close current panel
    close_all_dialogs(page)
    page.wait_for_timeout(500)

    # Find Img2Img y-position
    img2img_y = None
    for y, name in icon_map.items():
        if 'img2img' in name.lower() or 'image to image' in name.lower():
            img2img_y = y
            break

    if not img2img_y:
        img2img_y = 240
        print(f"  Using default y={img2img_y} for Img2Img")

    page.mouse.click(40, img2img_y)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel after Img2Img click: {panel}")

    if panel == 'img2img':
        # Map the Img2Img panel fully
        img2img_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var sn = panel.querySelector('.style-name');
            var ta = panel.querySelector('textarea');
            // Check for upload area
            var upload = panel.querySelector('[class*="upload"], [class*="drop"], input[type="file"]');
            // Check for sliders
            var sliders = panel.querySelectorAll('input[type="range"], [class*="slider"]');
            // Check for Structure/Color match controls
            var controls = [];
            for (var el of panel.querySelectorAll('[class*="control"], [class*="match"], [class*="strength"]')) {
                controls.push({
                    cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : '',
                    text: (el.innerText || '').trim().substring(0, 30)
                });
            }
            return {
                model: sn ? (sn.innerText || '').trim() : 'unknown',
                hasPrompt: !!ta,
                hasUpload: !!upload,
                sliderCount: sliders.length,
                controls: controls,
                panelText: (panel.innerText || '').substring(0, 500)
            };
        }""")
        print(f"  Model: {img2img_info.get('model')}")
        print(f"  Has prompt: {img2img_info.get('hasPrompt')}")
        print(f"  Has upload: {img2img_info.get('hasUpload')}")
        print(f"  Sliders: {img2img_info.get('sliderCount')}")
        print(f"  Controls: {json.dumps(img2img_info.get('controls', []))}")
        print(f"  Panel text:")
        for line in img2img_info.get('panelText', '').split('\n')[:20]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")

        screenshot(page, "p211_img2img_panel")

        # Try uploading a product image
        # Check if there's a file input
        has_file_input = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var input = panel.querySelector('input[type="file"]');
            return !!input;
        }""")
        print(f"  File input available: {has_file_input}")

        if has_file_input:
            # Upload a product image from artifacts
            import glob
            import os
            artifacts_dir = "/Users/ray/Documents/openclaw/artifacts/dzine"
            images = glob.glob(f"{artifacts_dir}/**/*.png", recursive=True) + \
                     glob.glob(f"{artifacts_dir}/**/*.jpg", recursive=True)
            if not images:
                # Check broader artifacts
                artifacts_dir = "/Users/ray/Documents/openclaw/artifacts"
                images = glob.glob(f"{artifacts_dir}/**/*.png", recursive=True) + \
                         glob.glob(f"{artifacts_dir}/**/*.jpg", recursive=True)

            if images:
                # Use the first available image
                image_path = images[0]
                print(f"  Uploading: {image_path}")
                page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return;
                    var input = panel.querySelector('input[type="file"]');
                    if (input) input.style.display = 'block';
                }""")
                file_input = page.query_selector('.c-gen-config.show input[type="file"]')
                if file_input:
                    file_input.set_input_files(image_path)
                    print("  File uploaded!")
                    page.wait_for_timeout(3000)
                    screenshot(page, "p211_img2img_uploaded")
            else:
                print("  No images found in artifacts/")
    else:
        print(f"  Could not open Img2Img (got: {panel})")

    # ================================================================
    # STEP 5: Credits check
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 5: Final Credits Status")
    print("=" * 70)

    credits = page.evaluate("""() => {
        // Look for credit display in header
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/) || t.match(/^[\\d.,]+\\s*credits/i)) {
                return t;
            }
        }
        // Also check for video credits
        var text = document.body.innerText || '';
        var match = text.match(/([\\d,.]+)\\s*video\\s*credits/i);
        return match ? match[0] : 'unknown';
    }""")
    print(f"  Credits: {credits}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 21 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
