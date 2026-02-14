"""Phase 113: Generate image with Ray character + test Upload mechanism.
P112 findings:
- Ray character exists! Slots: 1/60, in Character list (no Preset tag)
- Build Character: Quick Mode (1 image) or Training Mode (multiple images)
- Generate Images: 4 credits, Camera/Pose/Reference control, Fast/Normal/HQ
- Insert Character: 28 credits, Lasso/Brush/Auto marking
- Enhance & Upscale: Precision/Creative, 1.5x-4x, PNG/JPG
- Upload: no file input visible, likely file_chooser based

Goal: 1) Select Ray character and generate an image
      2) Test Upload mechanism (file_chooser)
      3) Explore Character Sheet
      4) Explore Generate 360° Video
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(6):
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
        if not found:
            break


def wait_for_canvas(page, max_wait=40):
    for i in range(max_wait):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    return False


def cleanup_tabs(ctx):
    pages = ctx.pages
    print(f"  Found {len(pages)} open tabs", flush=True)
    kept = False
    for p in pages:
        url = p.url or ""
        if "dzine.ai" in url:
            if kept:
                try:
                    p.close()
                except Exception:
                    pass
            else:
                kept = True
        elif url in ("", "about:blank", "chrome://newtab/"):
            try:
                p.close()
            except Exception:
                pass
    print(f"  Tabs after cleanup: {len(ctx.pages)}", flush=True)


def close_all_panels(page):
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
        for (var el of document.querySelectorAll('.popup-mount-node .ico-close')) el.click();
    }""")
    page.wait_for_timeout(1000)


def open_sidebar_tool(page, target_y):
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 766)  # Storyboard first
    page.wait_for_timeout(1500)
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, target_y)
    page.wait_for_timeout(2500)
    close_dialogs(page)


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    cleanup_tabs(ctx)

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  STEP 1: Open Character > Generate Images
    # ============================================================
    print("\n=== STEP 1: Open Character > Generate Images ===", flush=True)

    open_sidebar_tool(page, 306)

    # Click "Generate Images"
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="collapse-option"], button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Generate Images') && r.width > 100 && r.x < 350) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ============================================================
    #  STEP 2: Select Ray character
    # ============================================================
    print("\n=== STEP 2: Select Ray character ===", flush=True)

    # Click "Choose a Character" to open character list
    char_btn = page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, [class*="choose"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Choose a Character') && r.width > 100 && r.x < 300) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")

    if char_btn:
        page.mouse.click(char_btn['x'], char_btn['y'])
        page.wait_for_timeout(1500)
        print(f"  Opened character chooser", flush=True)

    # Find and click Ray in the character list
    ray_clicked = page.evaluate("""() => {
        // Look for Ray in character list items
        for (var el of document.querySelectorAll('.item, [class*="character-item"], button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Ray' && r.width > 50 && r.x > 300 && r.x < 700) {
                el.click();
                return {clicked: true, x: Math.round(r.x), y: Math.round(r.y), text: text};
            }
        }
        // Try broader search
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Ray' && r.width > 30 && r.width < 250 && r.height > 15 && r.height < 50) {
                el.click();
                return {clicked: true, x: Math.round(r.x), y: Math.round(r.y), text: text, broad: true};
            }
        }
        return {clicked: false};
    }""")
    print(f"  Ray click: {json.dumps(ray_clicked)}", flush=True)
    page.wait_for_timeout(2000)

    # Verify Ray is selected
    selection = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        // Check if a character avatar/thumbnail appears
        var avatar = null;
        for (var el of panel.querySelectorAll('img, [class*="avatar"], [class*="character-thumb"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 30 && r.width < 100 && r.x < 200) {
                avatar = {
                    tag: el.tagName,
                    src: el.src ? el.src.substring(0, 100) : null,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
                break;
            }
        }

        // Check for "Choose a Character" button text change
        var chooseBtn = null;
        for (var el of panel.querySelectorAll('button')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Character') || text.includes('Ray')) {
                var r = el.getBoundingClientRect();
                if (r.x < 300 && r.width > 80) {
                    chooseBtn = {text: text.substring(0, 40), x: Math.round(r.x), y: Math.round(r.y)};
                    break;
                }
            }
        }

        // Check if Generate button is still disabled
        var gen = panel.querySelector('.generative');
        var genInfo = gen ? {
            text: (gen.innerText || '').trim(),
            disabled: gen.disabled,
            class: (gen.className || '').toString().substring(0, 40),
        } : null;

        // Check warning text
        var warning = null;
        var text = (panel.innerText || '');
        if (text.includes('Please choose')) warning = 'Please choose a character';
        if (text.includes('Please enter')) warning = 'Please enter prompt';

        return {avatar: avatar, chooseBtn: chooseBtn, gen: genInfo, warning: warning};
    }""")
    print(f"  Selection: {json.dumps(selection, indent=2)}", flush=True)

    ss(page, "P113_01_ray_selected")

    # ============================================================
    #  STEP 3: Type a scene prompt + generate
    # ============================================================
    print("\n=== STEP 3: Type prompt + generate ===", flush=True)

    prompt_text = "Standing in a professional recording studio, presenting a pair of premium wireless headphones to the camera, confident smile, YouTube thumbnail pose"

    # Find the prompt area
    prompt_area = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        // Look for textarea or contenteditable
        var ta = panel.querySelector('textarea, [contenteditable="true"]');
        if (!ta) {
            // Try prompt-textarea class
            ta = panel.querySelector('.prompt-textarea');
        }
        if (ta) {
            var r = ta.getBoundingClientRect();
            return {
                tag: ta.tagName,
                class: (ta.className || '').toString().substring(0, 60),
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
            };
        }
        return null;
    }""")
    print(f"  Prompt area: {json.dumps(prompt_area)}", flush=True)

    if prompt_area:
        page.mouse.click(prompt_area['x'], prompt_area['y'])
        page.wait_for_timeout(500)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(prompt_text, delay=10)
        page.wait_for_timeout(1000)
        print(f"  Typed prompt ({len(prompt_text)} chars)", flush=True)

    # Check if Generate is now enabled
    gen_state = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var gen = panel.querySelector('.generative');
        if (!gen) return null;
        var r = gen.getBoundingClientRect();
        return {
            text: (gen.innerText || '').trim(),
            disabled: gen.disabled,
            x: Math.round(r.x + r.width/2),
            y: Math.round(r.y + r.height/2),
        };
    }""")
    print(f"  Generate button: {json.dumps(gen_state)}", flush=True)

    ss(page, "P113_02_prompt_typed")

    # Click Generate if enabled
    if gen_state and not gen_state.get('disabled'):
        initial_results = page.evaluate("() => document.querySelectorAll('.result-item').length")
        print(f"  Initial results: {initial_results}", flush=True)
        print(f"  Clicking Generate ({gen_state['text']})...", flush=True)
        page.mouse.click(gen_state['x'], gen_state['y'])
        page.wait_for_timeout(3000)

        # Monitor generation
        print("  Waiting for generation...", flush=True)
        for i in range(40):
            elapsed = (i + 1) * 3
            check = page.evaluate("""(initCount) => {
                var results = document.querySelectorAll('.result-item');
                var newCount = results.length;

                // Check newest result
                var newest = results.length > 0 ? results[0] : null;
                var newestText = newest ? (newest.innerText || '').trim().substring(0, 80) : '';
                var newestImg = newest ? newest.querySelector('img') : null;
                var imgLoaded = newestImg ? (newestImg.naturalWidth > 0) : false;

                // Check progress
                var progress = null;
                for (var el of document.querySelectorAll('.result-item')) {
                    var text = (el.innerText || '').trim();
                    var match = text.match(/(\\d+)%/);
                    if (match) { progress = match[1] + '%'; break; }
                }

                // Check button state
                var panel = document.querySelector('.c-gen-config.show');
                var gen = panel ? panel.querySelector('.generative') : null;
                var isGenerating = gen ? gen.disabled : false;

                return {
                    resultCount: newCount,
                    newResults: newCount - initCount,
                    newestText: newestText,
                    imgLoaded: imgLoaded,
                    progress: progress,
                    isGenerating: isGenerating,
                };
            }""", initial_results)

            if check.get('newResults', 0) > 0 and check.get('imgLoaded'):
                print(f"  New result with image at {elapsed}s!", flush=True)
                break

            if check.get('progress'):
                if i % 3 == 0:
                    print(f"  ...{elapsed}s progress={check['progress']} results={check['resultCount']}", flush=True)
            elif i % 5 == 0:
                print(f"  ...{elapsed}s results={check.get('resultCount')} gen={check.get('isGenerating')}", flush=True)

            page.wait_for_timeout(3000)

        ss(page, "P113_03_generation_result")

        # Check the result
        result = page.evaluate("""() => {
            var first = document.querySelector('.result-item');
            if (!first) return null;
            var text = (first.innerText || '').trim();
            var imgs = [];
            for (var img of first.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.width > 30 && r.height > 30) {
                    imgs.push({
                        src: (img.src || '').substring(0, 120),
                        w: Math.round(r.width), h: Math.round(r.height),
                        natural: img.naturalWidth + 'x' + img.naturalHeight,
                    });
                }
            }
            return {text: text.substring(0, 120), images: imgs.slice(0, 4)};
        }""")
        print(f"  Result: {json.dumps(result, indent=2)}", flush=True)
    else:
        print("  Generate button disabled — Ray might not be selected properly", flush=True)
        # Try to debug
        panel_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            return panel ? (panel.innerText || '').substring(0, 300) : 'no panel';
        }""")
        print(f"  Panel text: {panel_text[:200]}", flush=True)

    # ============================================================
    #  STEP 4: Upload mechanism — test file_chooser
    # ============================================================
    print("\n=== STEP 4: Upload mechanism ===", flush=True)

    # Go to Assets panel to test upload
    open_sidebar_tool(page, 136)  # Assets at y=136
    page.wait_for_timeout(1000)

    # The Upload sidebar icon (y=81) doesn't open a panel.
    # Let's check if clicking it directly triggers file_chooser.
    # First, try the Assets panel upload button.

    upload_btn_info = page.evaluate("""() => {
        // Find upload button in Assets panel
        var panel = document.querySelector('.panels.show');
        if (!panel) return null;
        var btn = panel.querySelector('.upload-image, [class*="upload"]');
        if (btn) {
            var r = btn.getBoundingClientRect();
            return {
                class: (btn.className || '').toString().substring(0, 60),
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
            };
        }
        return null;
    }""")
    print(f"  Assets upload btn: {json.dumps(upload_btn_info)}", flush=True)

    if upload_btn_info:
        print("  Testing file chooser on Assets upload button...", flush=True)
        try:
            with page.expect_file_chooser(timeout=3000) as fc_info:
                page.mouse.click(upload_btn_info['x'], upload_btn_info['y'])
            file_chooser = fc_info.value
            print(f"  FILE CHOOSER triggered!", flush=True)
            print(f"    Multiple: {file_chooser.is_multiple}", flush=True)
            # Don't actually upload, just confirm mechanism
            # Close the file chooser by pressing Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception as e:
            print(f"  No file chooser from Assets upload: {e}", flush=True)

    # Now test the sidebar Upload icon
    print("\n  Testing sidebar Upload icon...", flush=True)
    close_all_panels(page)
    page.wait_for_timeout(500)

    try:
        with page.expect_file_chooser(timeout=3000) as fc_info:
            page.mouse.click(40, 81)  # Upload icon
        file_chooser = fc_info.value
        print(f"  FILE CHOOSER from Upload icon!", flush=True)
        print(f"    Multiple: {file_chooser.is_multiple}", flush=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception as e:
        print(f"  No file chooser from Upload icon: {e}", flush=True)
        # Maybe it opens a panel that has upload
        page.wait_for_timeout(2000)
        check_panel = page.evaluate("""() => {
            var panels = [];
            for (var el of document.querySelectorAll('.panels.show, .c-gen-config.show, [class*="upload"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100) {
                    panels.push({
                        class: (el.className || '').toString().substring(0, 60),
                        text: (el.innerText || '').substring(0, 100),
                    });
                }
            }
            return panels;
        }""")
        print(f"  Panels after Upload click: {json.dumps(check_panel)}", flush=True)

    ss(page, "P113_04_upload_test")

    # ============================================================
    #  STEP 5: Explore Character Sheet
    # ============================================================
    print("\n=== STEP 5: Character Sheet ===", flush=True)

    open_sidebar_tool(page, 306)

    # Click "Character Sheet" option
    sheet_clicked = page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="collapse-option"], button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Character Sheet') && r.width > 100 && r.x < 350) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), text: text.substring(0, 40)};
            }
        }
        return null;
    }""")
    print(f"  Clicked: {json.dumps(sheet_clicked)}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    sheet_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show, .panels.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').substring(0, 500);
        var title = panel.querySelector('h5');

        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [class*="upload"], [class*="option"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 20 || r.height < 10) continue;
            elements.push({
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 50),
                text: (el.innerText || '').trim().substring(0, 30),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width),
            });
        }

        return {
            title: title ? (title.innerText || '').trim() : '',
            fullText: text,
            elements: elements.slice(0, 15),
        };
    }""")

    print(f"  Title: {sheet_panel.get('title')}", flush=True)
    print(f"  Full text:\n{sheet_panel.get('fullText', '')[:300]}", flush=True)
    print(f"\n  Elements ({len(sheet_panel.get('elements', []))}):", flush=True)
    for e in sheet_panel.get('elements', []):
        print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:25]}' ({e['x']},{e['y']}) w={e['w']}", flush=True)

    ss(page, "P113_05_character_sheet")

    # ============================================================
    #  STEP 6: Explore Generate 360° Video
    # ============================================================
    print("\n=== STEP 6: Generate 360° Video ===", flush=True)

    open_sidebar_tool(page, 306)

    video360_clicked = page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="collapse-option"], button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('360') && r.width > 100 && r.x < 350) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), text: text.substring(0, 50)};
            }
        }
        return null;
    }""")
    print(f"  Clicked: {json.dumps(video360_clicked)}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    video360_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show, .panels.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').substring(0, 500);

        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [class*="upload"], [class*="option"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 20 || r.height < 10) continue;
            elements.push({
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 50),
                text: (el.innerText || '').trim().substring(0, 30),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width),
            });
        }

        return {fullText: text, elements: elements.slice(0, 15)};
    }""")

    print(f"  Full text:\n{video360_panel.get('fullText', '')[:300]}", flush=True)
    print(f"\n  Elements ({len(video360_panel.get('elements', []))}):", flush=True)
    for e in video360_panel.get('elements', []):
        print(f"    <{e['tag']}> .{e['class'][:40]} '{e['text'][:25]}' ({e['x']},{e['y']}) w={e['w']}", flush=True)

    ss(page, "P113_06_360_video")

    # Final credits
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,]+$/) && parseInt(text.replace(/,/g, '')) > 1000 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\n  Credits: {credits}", flush=True)

    ss(page, "P113_07_final")
    print(f"\n\n===== PHASE 113 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
