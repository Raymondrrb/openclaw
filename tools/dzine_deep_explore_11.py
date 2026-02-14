#!/usr/bin/env python3
"""Dzine Deep Exploration Part 11 — Fix Nano Banana Pro + Video Check + Lip Sync.

1. Fix model selection: navigate style picker categories to find Nano Banana Pro
2. Check if AI Video from Part 10 completed
3. Test Nano Banana Pro generation with product prompt
4. Explore Lip Sync panel
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


def count_results(page):
    return page.evaluate("""() => {
        return document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]').length;
    }""")


def get_panel_text(page):
    return page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (p) return p.innerText.substring(0, 2000);
        p = document.querySelector('.panels.show');
        if (p) return p.innerText.substring(0, 2000);
        return 'NO PANEL';
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 11")
    print("Fix Nano Banana Pro + Video Check + Lip Sync")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: Check AI Video Result from Part 10
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Check AI Video Result")
    print("=" * 70)

    # Check credits (should be 8.844 if video was charged)
    credits = page.evaluate("""() => {
        var spans = document.querySelectorAll('span');
        for (var s of spans) {
            var text = (s.innerText || '').trim();
            var rect = s.getBoundingClientRect();
            if (rect.y < 40 && rect.y > 5 && /^[0-9]+\\.[0-9]+$/.test(text)) {
                return text;
            }
        }
        return '';
    }""")
    print(f"  Video credits: {credits}")

    # Check for video results in the panel
    video_results = page.evaluate("""() => {
        var items = document.querySelectorAll('.result-item');
        var videos = [];
        for (var item of items) {
            var rect = item.getBoundingClientRect();
            if (rect.height === 0) continue;
            var cls = (typeof item.className === 'string') ? item.className : (item.getAttribute('class') || '');
            if (cls.includes('video') || cls.includes('i2v')) {
                var video = item.querySelector('video');
                var img = item.querySelector('img');
                var status = '';
                for (var el of item.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    if (t.includes('Waiting') || t.includes('Complete') || t.includes('Failed') || t.includes('Ready')) {
                        status = t.substring(0, 60);
                        break;
                    }
                }
                videos.push({
                    class: cls.substring(0, 60),
                    hasVideo: !!video,
                    videoSrc: video ? (video.src || '').substring(0, 120) : '',
                    hasImg: !!img,
                    imgSrc: img ? (img.src || '').substring(0, 120) : '',
                    status: status,
                    y: Math.round(rect.y)
                });
            }
        }
        return videos;
    }""")
    print(f"  Video result items ({len(video_results)}):")
    for vr in video_results:
        print(f"    class: {vr['class']}")
        print(f"    video={vr['hasVideo']} img={vr['hasImg']} status='{vr['status']}'")
        if vr['videoSrc']:
            print(f"    src: {vr['videoSrc']}")

    # Also scroll Results panel to check for completed videos
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Look for any "Image-to-Video" sections
    i2v_sections = page.evaluate("""() => {
        var results = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.startsWith('Image-to-Video') && el.offsetHeight > 0 && el.offsetHeight < 100) {
                var rect = el.getBoundingClientRect();
                results.push({
                    text: text.substring(0, 80),
                    y: Math.round(rect.y),
                    tag: el.tagName
                });
            }
        }
        return results;
    }""")
    print(f"\n  Image-to-Video sections ({len(i2v_sections)}):")
    for s in i2v_sections:
        print(f"    '{s['text']}' at y={s['y']}")

    screenshot(page, "p181_video_check")

    # ================================================================
    # TASK 2: Fix Nano Banana Pro Selection
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Fix Nano Banana Pro Model Selection")
    print("=" * 70)

    # Navigate to Txt2Img
    page.mouse.click(40, 766)  # Storyboard first
    page.wait_for_timeout(1500)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2500)

    # Check current model
    current = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Current model: {current}")

    # Open style picker
    print("  Opening style picker...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var btn = panel.querySelector('button.style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Map categories in the style picker left sidebar
    categories = page.evaluate("""() => {
        var picker = document.querySelector('.style-list-panel');
        if (!picker) return [];
        // Look for category tabs/items
        var cats = picker.querySelectorAll('.category-item, .tab-item, [class*="category"], [class*="tab"]');
        var results = [];
        for (var cat of cats) {
            var rect = cat.getBoundingClientRect();
            if (rect.height > 0 && rect.width < 200) {
                results.push({
                    text: (cat.innerText || '').trim(),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                    active: ((typeof cat.className === 'string') ? cat.className : '').includes('active') || ((typeof cat.className === 'string') ? cat.className : '').includes('selected')
                });
            }
        }
        return results;
    }""")

    if not categories:
        # Try a different approach - look for left sidebar items
        categories = page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return [];
            var items = [];
            var allDivs = picker.querySelectorAll('div, span, a');
            for (var el of allDivs) {
                var rect = el.getBoundingClientRect();
                // Left sidebar items should be at x < 300 and narrow
                if (rect.x < 300 && rect.width < 150 && rect.height > 15 && rect.height < 50) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 30 && !text.includes('\\n')) {
                        // Deduplicate by text
                        var exists = false;
                        for (var item of items) {
                            if (item.text === text) { exists = true; break; }
                        }
                        if (!exists) {
                            items.push({
                                text: text,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                tag: el.tagName,
                                class: ((typeof el.className === 'string') ? el.className : '').substring(0, 40)
                            });
                        }
                    }
                }
            }
            return items.slice(0, 25);
        }""")

    print(f"  Style picker categories ({len(categories)}):")
    for cat in categories:
        print(f"    '{cat['text']}' at ({cat.get('x', 0)},{cat.get('y', 0)})")

    # Now look at what's visible in the main content area
    style_items = page.evaluate("""() => {
        var picker = document.querySelector('.style-list-panel');
        if (!picker) return [];
        var items = picker.querySelectorAll('[class*="style-item"]');
        var results = [];
        for (var item of items) {
            var rect = item.getBoundingClientRect();
            if (rect.height > 0 && rect.y > 0) {
                var text = (item.innerText || '').trim();
                results.push({
                    text: text.substring(0, 40),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height)
                });
            }
        }
        return results.slice(0, 20);
    }""")
    print(f"\n  Visible style items ({len(style_items)}):")
    for si in style_items[:10]:
        print(f"    '{si['text']}' at ({si['x']},{si['y']}) {si['w']}x{si['h']}")

    screenshot(page, "p181_style_picker_open")

    # Try clicking "All styles" category to see all models
    clicked_all = page.evaluate("""() => {
        var picker = document.querySelector('.style-list-panel');
        if (!picker) return false;
        for (var el of picker.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'All styles' || text === 'All Styles') {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0 && rect.height < 50) {
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    print(f"\n  Clicked 'All styles': {clicked_all}")
    page.wait_for_timeout(1000)

    # Now search for Nano Banana Pro specifically among visible items
    nbp_found = page.evaluate("""() => {
        var picker = document.querySelector('.style-list-panel');
        if (!picker) return {found: false};
        var items = picker.querySelectorAll('[class*="style-item"]');
        for (var item of items) {
            var text = (item.innerText || '').trim();
            if (text.includes('Nano Banana Pro')) {
                var rect = item.getBoundingClientRect();
                return {
                    found: true,
                    text: text,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    visible: rect.height > 0
                };
            }
        }
        // Also check if we need to scroll
        var scrollable = picker.querySelector('.style-list, [class*="scroll"], [class*="content"]');
        return {
            found: false,
            totalItems: items.length,
            scrollable: scrollable ? {
                scrollHeight: scrollable.scrollHeight,
                clientHeight: scrollable.clientHeight,
                scrollTop: scrollable.scrollTop
            } : null
        };
    }""")
    print(f"  Nano Banana Pro search: {json.dumps(nbp_found)}")

    # If not found, try scrolling through the content
    if not nbp_found.get("found"):
        print("  Scrolling to find Nano Banana Pro...")
        # Try scrolling the style list content
        for scroll_pos in range(0, 3000, 500):
            found = page.evaluate("""(scrollPos) => {
                var picker = document.querySelector('.style-list-panel');
                if (!picker) return {found: false};
                // Find scrollable container
                var containers = picker.querySelectorAll('div');
                for (var c of containers) {
                    if (c.scrollHeight > c.clientHeight + 50 && c.clientHeight > 200) {
                        c.scrollTop = scrollPos;
                        break;
                    }
                }
                // Check for Nano Banana Pro
                var items = picker.querySelectorAll('[class*="style-item"]');
                for (var item of items) {
                    var text = (item.innerText || '').trim();
                    if (text.includes('Nano Banana Pro')) {
                        var rect = item.getBoundingClientRect();
                        if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                            item.click();
                            return {found: true, text: text, scrollPos: scrollPos};
                        }
                    }
                }
                return {found: false, scrollPos: scrollPos};
            }""", scroll_pos)
            if found.get("found"):
                print(f"    FOUND at scroll={found['scrollPos']}! Clicked.")
                break
        else:
            print("    Not found by scrolling. Trying search...")
            # Use the search input with exact text
            page.evaluate("""() => {
                var picker = document.querySelector('.style-list-panel');
                if (!picker) return;
                var input = picker.querySelector('input[type="text"]');
                if (input) {
                    input.value = '';
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.focus();
                }
            }""")
            page.wait_for_timeout(300)
            page.keyboard.type("Nano Banana", delay=20)
            page.wait_for_timeout(2000)

            # Check results
            search_results = page.evaluate("""() => {
                var picker = document.querySelector('.style-list-panel');
                if (!picker) return [];
                var items = picker.querySelectorAll('[class*="style-item"]');
                var results = [];
                for (var item of items) {
                    var rect = item.getBoundingClientRect();
                    if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                        results.push({
                            text: (item.innerText || '').trim().substring(0, 50),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y)
                        });
                    }
                }
                return results;
            }""")
            print(f"    Search results for 'Nano Banana': {json.dumps(search_results)}")

            # Click the one that says "Nano Banana Pro"
            clicked_nbp = page.evaluate("""() => {
                var picker = document.querySelector('.style-list-panel');
                if (!picker) return false;
                var items = picker.querySelectorAll('[class*="style-item"]');
                for (var item of items) {
                    var text = (item.innerText || '').trim();
                    var rect = item.getBoundingClientRect();
                    if (text.includes('Nano Banana Pro') && rect.height > 0 && rect.y > 0) {
                        item.click();
                        return true;
                    }
                }
                // If not found, try clicking any "Nano Banana" item
                for (var item of items) {
                    var text = (item.innerText || '').trim();
                    var rect = item.getBoundingClientRect();
                    if (text.includes('Nano Banana') && rect.height > 0 && rect.y > 0) {
                        item.click();
                        return text;
                    }
                }
                return false;
            }""")
            print(f"    Clicked Nano Banana Pro: {clicked_nbp}")

    page.wait_for_timeout(1000)

    # Close style picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Verify model changed
    new_model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : 'unknown';
    }""")
    print(f"\n  Model after selection: {new_model}")

    if "Nano Banana" in new_model:
        print("  SUCCESS! Nano Banana Pro selected!")
    else:
        print(f"  FAILED — model is still '{new_model}'")

    screenshot(page, "p181_model_selected")

    # ================================================================
    # TASK 3: Generate with Nano Banana Pro (if selected)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Generate with Nano Banana Pro")
    print("=" * 70)

    # Fill prompt
    product_prompt = "A pair of premium wireless over-ear headphones with brushed aluminum finish, memory foam leather ear cushions, clean white studio background. Professional product photography, three-point lighting, razor-sharp focus, commercial grade image. No text, no watermarks."

    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var ta = panel.querySelector('textarea');
        if (ta) { ta.focus(); ta.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    page.keyboard.type(product_prompt, delay=2)
    page.wait_for_timeout(500)

    print(f"  Prompt filled ({len(product_prompt)} chars)")

    # Select Normal mode (4 credits - user says don't economize)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        for (var btn of panel.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            if (text === 'Normal') {
                var cls = (typeof btn.className === 'string') ? btn.className : '';
                if (cls.includes('options') && !cls.includes('selected')) {
                    btn.click();
                    return;
                }
            }
        }
    }""")
    page.wait_for_timeout(300)

    # Generate
    before_count = count_results(page)
    gen_info = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {};
        var btn = panel.querySelector('.generative');
        if (!btn) return {};
        var cls = (typeof btn.className === 'string') ? btn.className : '';
        return {
            text: (btn.innerText || '').trim(),
            ready: cls.includes('ready'),
            disabled: btn.disabled
        };
    }""")
    print(f"  Generate button: {json.dumps(gen_info)}")

    if gen_info.get("ready"):
        print(f"\n  >>> GENERATING ({new_model}, Normal, 4 credits) <<<")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var btn = panel.querySelector('.generative.ready');
            if (btn && !btn.disabled) btn.click();
        }""")

        start = time.time()
        while time.time() - start < 90:
            page.wait_for_timeout(3000)
            elapsed = int(time.time() - start)

            after_count = count_results(page)
            if after_count > before_count:
                print(f"\n  GENERATION COMPLETE! ({elapsed}s, new images: {after_count - before_count})")
                break

            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var txt = (el.innerText || '').trim();
                    if (/^[0-9]{1,3}%$/.test(txt)) {
                        var r = el.getBoundingClientRect();
                        if (r.x > 1000) return txt;
                    }
                }
                return '';
            }""")
            if progress:
                print(f"    Progress: {progress} ({elapsed}s)")
        else:
            final = count_results(page)
            print(f"\n  TIMEOUT. Results: {before_count} -> {final}")

        screenshot(page, "p181_nanobp_generation")

        # Get latest URLs
        latest = page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            var urls = [];
            for (var img of imgs) urls.push(img.src);
            return urls.slice(-4);
        }""")
        print("  Latest URLs:")
        for u in latest:
            print(f"    {u[:150]}")

    # ================================================================
    # TASK 4: Explore Lip Sync Panel
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Lip Sync Panel Exploration")
    print("=" * 70)

    # Reload to clear panels
    page.goto("https://www.dzine.ai/canvas?id=19861203")
    page.wait_for_timeout(5000)

    # Dismiss dialogs
    page.evaluate("""() => {
        for (var i = 0; i < 5; i++) {
            for (var text of ['Not now', 'Close', 'Never show again', 'Got it', 'Skip', 'Later']) {
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === text && btn.offsetHeight > 0) btn.click();
                }
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # Click Lip Sync sidebar
    print("  Opening Lip Sync panel...")
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)

    # Map the Lip Sync panel thoroughly
    lip_sync = page.evaluate("""() => {
        var panel = document.querySelector('.lip-sync-config-panel.show, .lip-sync-panel-v2');
        if (!panel) {
            // Try gen config panel
            panel = document.querySelector('.c-gen-config.show');
        }
        if (!panel) return {found: false};

        var cls = (typeof panel.className === 'string') ? panel.className : (panel.getAttribute('class') || '');
        var rect = panel.getBoundingClientRect();

        // Map all interactive elements
        var buttons = [];
        for (var btn of panel.querySelectorAll('button, [role="button"]')) {
            var br = btn.getBoundingClientRect();
            if (br.height > 0) {
                var bc = (typeof btn.className === 'string') ? btn.className : '';
                buttons.push({
                    text: (btn.innerText || '').trim().substring(0, 40),
                    class: bc.substring(0, 50),
                    x: Math.round(br.x),
                    y: Math.round(br.y),
                    w: Math.round(br.width),
                    h: Math.round(br.height),
                    selected: bc.includes('selected') || bc.includes('active'),
                    disabled: btn.disabled
                });
            }
        }

        // Map inputs/textareas
        var inputs = [];
        for (var inp of panel.querySelectorAll('input, textarea')) {
            var ir = inp.getBoundingClientRect();
            if (ir.height > 0) {
                inputs.push({
                    type: inp.type || inp.tagName,
                    placeholder: (inp.placeholder || '').substring(0, 50),
                    value: (inp.value || '').substring(0, 50),
                    x: Math.round(ir.x),
                    y: Math.round(ir.y),
                    w: Math.round(ir.width)
                });
            }
        }

        // Map sliders
        var sliders = [];
        for (var s of panel.querySelectorAll('.c-slider, .ant-slider, [class*="slider"]')) {
            var sr = s.getBoundingClientRect();
            if (sr.height > 0) {
                sliders.push({
                    x: Math.round(sr.x),
                    y: Math.round(sr.y),
                    w: Math.round(sr.width)
                });
            }
        }

        // Map upload areas
        var uploads = [];
        for (var u of panel.querySelectorAll('.pick-image, .upload-image-btn, [class*="upload"]')) {
            var ur = u.getBoundingClientRect();
            if (ur.height > 0) {
                uploads.push({
                    text: (u.innerText || '').trim().substring(0, 50),
                    class: ((typeof u.className === 'string') ? u.className : '').substring(0, 40),
                    x: Math.round(ur.x),
                    y: Math.round(ur.y),
                    w: Math.round(ur.width),
                    h: Math.round(ur.height)
                });
            }
        }

        return {
            found: true,
            class: cls.substring(0, 80),
            pos: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
            text: (panel.innerText || '').substring(0, 600),
            buttons: buttons,
            inputs: inputs,
            sliders: sliders,
            uploads: uploads
        };
    }""")

    if lip_sync.get("found"):
        print(f"  Panel class: {lip_sync['class']}")
        print(f"  Panel pos: ({lip_sync['pos']['x']},{lip_sync['pos']['y']}) {lip_sync['pos']['w']}x{lip_sync['pos']['h']}")
        print(f"\n  Panel text (first 400 chars):")
        for line in lip_sync['text'].split('\n')[:20]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")

        print(f"\n  Buttons ({len(lip_sync['buttons'])}):")
        for b in lip_sync['buttons']:
            flags = []
            if b.get('selected'): flags.append('SELECTED')
            if b.get('disabled'): flags.append('DISABLED')
            print(f"    '{b['text'][:30]}' at ({b['x']},{b['y']}) {b['w']}x{b['h']} {' '.join(flags)}")

        print(f"\n  Inputs ({len(lip_sync['inputs'])}):")
        for i in lip_sync['inputs']:
            print(f"    {i['type']} '{i['placeholder'][:30]}' at ({i['x']},{i['y']})")

        print(f"\n  Uploads ({len(lip_sync['uploads'])}):")
        for u in lip_sync['uploads']:
            print(f"    '{u['text'][:30]}' class={u['class'][:30]} at ({u['x']},{u['y']}) {u['w']}x{u['h']}")

    else:
        print("  Lip Sync panel NOT found!")
        # Check what's visible
        panel_text = get_panel_text(page)
        print(f"  Active panel text: {panel_text[:300]}")

    screenshot(page, "p181_lip_sync_panel")

    # Close Lip Sync if it's the full-canvas overlay
    page.evaluate("""() => {
        var panel = document.querySelector('.lip-sync-config-panel.show');
        if (panel) {
            var close = panel.querySelector('.ico-close');
            if (close) { close.click(); return 'closed'; }
            panel.classList.remove('show');
            return 'removed show';
        }
        return 'no panel';
    }""")
    page.wait_for_timeout(500)

    # ================================================================
    # TASK 5: Check Video Generation Completion (revisit)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Final Video Status Check")
    print("=" * 70)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Scroll results panel to find video result
    video_status = page.evaluate("""() => {
        // Find all result sections
        var results = [];
        var allElements = document.querySelectorAll('[class*="result"]');
        for (var el of allElements) {
            var text = (el.innerText || '');
            if (text.includes('Image-to-Video') || text.includes('video-result')) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 50) {
                    var video = el.querySelector('video');
                    var videoSrc = '';
                    if (video) {
                        var source = video.querySelector('source');
                        videoSrc = (source ? source.src : video.src) || '';
                    }
                    results.push({
                        class: ((typeof el.className === 'string') ? el.className : '').substring(0, 60),
                        hasVideo: !!video,
                        videoSrc: videoSrc.substring(0, 150),
                        text: text.substring(0, 200),
                        y: Math.round(rect.y),
                        h: Math.round(rect.height)
                    });
                }
            }
        }
        return results;
    }""")
    print(f"  Video sections ({len(video_status)}):")
    for vs in video_status[:5]:
        print(f"    class: {vs['class']}")
        print(f"    video={vs['hasVideo']} src={vs['videoSrc'][:100]}")
        # Extract status from text
        text_lines = [l.strip() for l in vs['text'].split('\n') if l.strip()][:5]
        for line in text_lines:
            print(f"    > {line[:60]}")

    screenshot(page, "p181_final_state")

    # Final credits check
    final_credits = page.evaluate("""() => {
        var spans = document.querySelectorAll('span');
        for (var s of spans) {
            var text = (s.innerText || '').trim();
            var rect = s.getBoundingClientRect();
            if (rect.y < 40 && rect.y > 5 && /^[0-9]+\\.[0-9]+$/.test(text)) {
                return text;
            }
        }
        return '';
    }""")
    print(f"\n  Final video credits: {final_credits}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 11 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
