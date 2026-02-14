#!/usr/bin/env python3
"""Dzine Deep Exploration Part 24 — End-to-End Video Workflow + Character + Image Editor.

Part 23 findings:
- Image download via URL extraction WORKS (static.dzine.ai URLs, no auth)
- Chat Editor: model btn at (492,926), input is contenteditable div at (735,918)
- Img2Img HQ: 8 credits, Advanced has Negative Prompt (1600 chars) + Seed
- Color Match ON shows "Canvas" dropdown + palette
- Storyboard: V1/V2, @mentions, 6 credits, 1000 chars
- Assets at y=155, AI Video at y=370, Storyboard at y=778, Image Editor at y=698

Part 24 goals:
1. End-to-end: 4K image → AI Video (Wan 2.1 = 6 credits, cheapest)
2. Character tool — find correct sidebar position
3. Image Editor — try clicking at y=698 with different approach
4. Test Expression Edit from toolbar (top bar buttons)
5. Map all top toolbar buttons
"""

import json
import os
import sys
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def get_active_panel(page):
    return page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        var text = (panel.innerText || '').substring(0, 100).trim();
        if (text.startsWith('Text to Image') || text.startsWith('Text-to-Image')) return 'txt2img';
        if (text.startsWith('AI Video')) return 'ai_video';
        if (text.startsWith('Enhance')) return 'enhance';
        if (text.startsWith('Motion Control')) return 'motion';
        if (text.startsWith('Face Swap')) return 'face_swap';
        if (text.startsWith('Image-to-Image')) return 'img2img';
        if (text.startsWith('Character')) return 'character';
        if (text.startsWith('Instant Storyboard')) return 'storyboard';
        if (text.startsWith('Assets')) return 'assets';
        if (text.startsWith('Lip Sync')) return 'lip_sync';
        if (text.startsWith('Video Editor')) return 'video_editor';
        return 'unknown:' + text.substring(0, 50);
    }""")


def close_panels(page):
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 24")
    print("End-to-End Video + Character + Image Editor + Toolbar")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: Map Complete Sidebar by Text Content
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Map Sidebar Icons by Text Content")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    sidebar_map = page.evaluate("""() => {
        // Find all text elements in the left sidebar area (x < 60)
        var items = [];
        var knownTools = ['Upload', 'Assets', 'Txt2Img', 'Img2Img', 'Character',
                         'AI Video', 'Lip Sync', 'Video Editor', 'Motion Control',
                         'Enhance & Upscale', 'Image Editor', 'Instant Storyboard'];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            // Check for multi-line text (sidebar labels are often wrapped)
            var lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
            if (lines.length <= 2 && lines.length > 0) {
                var joined = lines.join(' ');
                for (var known of knownTools) {
                    if (joined === known || (lines.length === 2 && (lines[0] + ' ' + lines[1]) === known)) {
                        var rect = el.getBoundingClientRect();
                        if (rect.x < 60 && rect.height > 0 && rect.height < 60) {
                            items.push({
                                name: known,
                                x: Math.round(rect.x + rect.width / 2),
                                y: Math.round(rect.y + rect.height / 2),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height)
                            });
                        }
                    }
                }
            }
        }
        // Deduplicate by name (keep first match)
        var seen = {};
        var unique = [];
        for (var item of items) {
            if (!seen[item.name]) {
                seen[item.name] = true;
                unique.push(item);
            }
        }
        return unique.sort((a, b) => a.y - b.y);
    }""")

    print(f"  Sidebar tools ({len(sidebar_map)}):")
    for s in sidebar_map:
        print(f"    y={s['y']:3d}  x={s['x']:2d}  {s['w']:2d}x{s['h']:2d}  {s['name']}")

    # Build a quick lookup
    sidebar_y = {}
    for s in sidebar_map:
        sidebar_y[s['name']] = s['y']

    # ================================================================
    # TASK 2: Map Top Toolbar Buttons
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Map Top Toolbar Buttons")
    print("=" * 70)

    toolbar = page.evaluate("""() => {
        // Top toolbar is the row of buttons above the canvas (y < 60 or so)
        var items = [];
        var allBtns = document.querySelectorAll('button, [role="button"]');
        for (var btn of allBtns) {
            var rect = btn.getBoundingClientRect();
            if (rect.y > 25 && rect.y < 70 && rect.height > 10 && rect.height < 50) {
                var text = (btn.innerText || btn.getAttribute('title') || btn.getAttribute('aria-label') || '').trim();
                var cls = (typeof btn.className === 'string') ? btn.className : '';
                if (text.length > 0 && text.length < 30) {
                    items.push({
                        text: text,
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2),
                        cls: cls.substring(0, 30)
                    });
                }
            }
        }
        // Also check for icon buttons without text (SVG icons)
        for (var el of document.querySelectorAll('[class*="tool-item"], [class*="toolbar-btn"]')) {
            var rect = el.getBoundingClientRect();
            if (rect.y > 25 && rect.y < 70 && rect.height > 0) {
                var text = (el.getAttribute('title') || el.getAttribute('data-tooltip') || '').trim();
                if (text) {
                    items.push({text: text, x: Math.round(rect.x + rect.width / 2), y: Math.round(rect.y + rect.height / 2)});
                }
            }
        }
        return items;
    }""")

    print(f"  Toolbar buttons ({len(toolbar)}):")
    for t in sorted(toolbar, key=lambda x: x['x']):
        print(f"    x={t['x']:4d}  y={t['y']:2d}  '{t['text']}'")

    # Also map the second toolbar row (the image editing tools)
    toolbar2 = page.evaluate("""() => {
        var items = [];
        // The editing toolbar appears around y=47 area
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var rect = el.getBoundingClientRect();
            // Second toolbar row (typically y between 38-55)
            if (rect.y >= 38 && rect.y <= 55 && rect.height > 15 && rect.height < 40
                && rect.width > 20 && rect.width < 120
                && text.length > 2 && text.length < 25) {
                var cls = (typeof el.className === 'string') ? el.className : '';
                if (cls.includes('tool') || cls.includes('btn') || el.tagName === 'BUTTON') {
                    items.push({text: text, x: Math.round(rect.x + rect.width / 2), y: Math.round(rect.y + rect.height / 2)});
                }
            }
        }
        // Deduplicate
        var seen = {};
        var unique = [];
        for (var item of items) {
            if (!seen[item.text]) {
                seen[item.text] = true;
                unique.push(item);
            }
        }
        return unique.sort((a, b) => a.x - b.x);
    }""")

    print(f"\n  Editing toolbar ({len(toolbar2)}):")
    for t in toolbar2:
        print(f"    x={t['x']:4d}  y={t['y']:2d}  '{t['text']}'")

    # ================================================================
    # TASK 3: End-to-End — Place 4K Result on Canvas → AI Video
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: End-to-End — 4K Result → AI Video (Wan 2.1)")
    print("=" * 70)

    # Step 1: Click on the latest txt2img result to place on canvas
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Find the 4K txt2img result (5440x3060) and click to place on canvas
    placed = page.evaluate("""() => {
        var items = document.querySelectorAll('.result-item');
        for (var item of items) {
            var cls = (typeof item.className === 'string') ? item.className : '';
            if (cls.includes('text-to-image')) {
                var img = item.querySelector('img');
                if (img && img.naturalWidth === 5440) {
                    img.click();
                    return {placed: true, w: img.naturalWidth, h: img.naturalHeight};
                }
            }
        }
        // Fallback: click first txt2img result
        for (var item of items) {
            var cls = (typeof item.className === 'string') ? item.className : '';
            if (cls.includes('text-to-image')) {
                var img = item.querySelector('img');
                if (img) {
                    img.click();
                    return {placed: true, w: img.naturalWidth, h: img.naturalHeight, fallback: true};
                }
            }
        }
        return {placed: false};
    }""")
    print(f"  Placed on canvas: {json.dumps(placed)}")
    page.wait_for_timeout(2000)

    # Step 2: Use AI Video action from results (auto-populates start frame)
    print("  Opening AI Video from result actions...")

    # Hover on the result to show action buttons
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Scroll results to show txt2img section
    page.evaluate("""() => {
        var container = document.querySelector('[class*="result-container"], [class*="result-list"]');
        if (container) container.scrollTop = 0;
    }""")
    page.wait_for_timeout(500)

    # Click "AI Video" numbered button [1] from the txt2img results
    ai_video_clicked = page.evaluate("""() => {
        // Find Txt2Img results section
        var resultSections = document.querySelectorAll('[class*="result-group"], .result-item');
        for (var item of resultSections) {
            var cls = (typeof item.className === 'string') ? item.className : '';
            if (!cls.includes('text-to-image')) continue;

            // Find the AI Video action row
            var parent = item.closest('[class*="result-group"]') || item.parentElement;
            if (!parent) continue;

            var btnContainers = parent.querySelectorAll('.btn-container');
            for (var c of btnContainers) {
                var parentEl = c.parentElement;
                var parentText = (parentEl ? parentEl.innerText || '' : '').trim();
                if (parentText.startsWith('AI Video')) {
                    var btns = c.querySelectorAll('.btn');
                    if (btns.length > 0) {
                        btns[0].click();
                        return {clicked: true, text: 'AI Video [1]'};
                    }
                }
            }
        }

        // Fallback: find any AI Video button in visible results
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            if (parent && (parent.innerText || '').trim().startsWith('AI Video')) {
                var rect = c.getBoundingClientRect();
                if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                    var btns = c.querySelectorAll('.btn');
                    if (btns.length > 0) {
                        btns[0].click();
                        return {clicked: true, text: 'AI Video [1] (fallback)', y: Math.round(rect.y)};
                    }
                }
            }
        }
        return {clicked: false};
    }""")
    print(f"  AI Video button: {json.dumps(ai_video_clicked)}")
    page.wait_for_timeout(3000)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'ai_video':
        # Map the AI Video panel state
        video_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var text = (panel.innerText || '');
            // Check if start frame is populated
            var pickImage = panel.querySelector('button.pick-image');
            var hasFrame = pickImage ? !pickImage.classList.contains('has-guide') : false;
            // Also check for image preview in the upload area
            var preview = panel.querySelector('img[class*="preview"], img[src*="static.dzine.ai"]');
            // Get model info
            var modelSel = panel.querySelector('.custom-selector-wrapper');
            var modelText = modelSel ? (modelSel.innerText || '').trim() : 'unknown';
            // Generate button
            var genBtn = null;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Generate')) {
                    genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                }
            }
            return {
                hasStartFrame: hasFrame || !!preview,
                previewSrc: preview ? preview.src.substring(0, 80) : 'none',
                model: modelText,
                genBtn: genBtn,
                panelText: text.substring(0, 400)
            };
        }""")
        print(f"  Has start frame: {video_state.get('hasStartFrame')}")
        print(f"  Preview: {video_state.get('previewSrc', 'none')}")
        print(f"  Model: {video_state.get('model')}")
        print(f"  Generate: {json.dumps(video_state.get('genBtn'))}")

        screenshot(page, "p241_ai_video_setup")

        # Select Wan 2.1 (cheapest at 6 credits) if not already selected
        current_model = video_state.get('model', '')
        if 'Wan 2.1' not in current_model:
            print("  Selecting Wan 2.1 model...")
            # Click model selector
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                var sel = panel.querySelector('.custom-selector-wrapper');
                if (sel) sel.click();
            }""")
            page.wait_for_timeout(1000)

            # Click Wan 2.1
            wan_clicked = page.evaluate("""() => {
                var items = document.querySelectorAll('[class*="model-item"], [class*="selector-item"]');
                for (var item of items) {
                    if ((item.innerText || '').includes('Wan 2.1') && item.offsetHeight > 0) {
                        item.click();
                        return true;
                    }
                }
                // Broader search
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Wan 2.1') && el.offsetHeight > 0 && el.offsetHeight < 60) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            print(f"  Wan 2.1 selected: {wan_clicked}")
            page.wait_for_timeout(500)

        # Select Static Shot camera
        print("  Setting Static Shot camera...")
        # Expand camera
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var camBtn = panel.querySelector('.camera-movement-btn');
            if (camBtn) camBtn.click();
        }""")
        page.wait_for_timeout(1500)

        # Click Free Selection tab
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Free Selection' && el.offsetHeight > 0 && el.offsetHeight < 40) {
                    el.click(); return;
                }
            }
        }""")
        page.wait_for_timeout(1000)

        # Select Static Shot
        static_pos = page.evaluate("""(name) => {
            var items = document.querySelectorAll('.selection-item');
            for (var item of items) {
                if ((item.innerText || '').trim().includes(name)) {
                    var opts = item.querySelector('.selection-options');
                    if (opts) {
                        var rect = opts.getBoundingClientRect();
                        return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                    }
                }
            }
            return null;
        }""", "Static Shot")
        if static_pos:
            page.mouse.click(static_pos['x'], static_pos['y'])
            page.wait_for_timeout(500)
            # Verify
            is_selected = page.evaluate("""() => {
                var items = document.querySelectorAll('.selection-item');
                for (var item of items) {
                    if ((item.innerText || '').includes('Static Shot')) {
                        return !!item.querySelector('.option.selected-option');
                    }
                }
                return false;
            }""")
            print(f"  Static Shot selected: {is_selected}")
        else:
            print("  Static Shot position not found")

        # Close camera overlay
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)

        # Fill prompt
        prompt = "Premium wireless headphones slowly rotating on a clean white surface, studio lighting, product commercial, smooth motion, professional"
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

        # Check final state before generating
        final_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var genBtn = null;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Generate')) {
                    genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                }
            }
            var modelSel = panel.querySelector('.custom-selector-wrapper');
            return {
                model: modelSel ? (modelSel.innerText || '').trim() : 'unknown',
                genBtn: genBtn
            };
        }""")
        print(f"  Final model: {final_state.get('model')}")
        print(f"  Generate: {json.dumps(final_state.get('genBtn'))}")

        screenshot(page, "p241_ai_video_ready")

        # SAFETY: Check we're still on AI Video
        if get_active_panel(page) == 'ai_video':
            gen_text = (final_state.get('genBtn') or {}).get('text', '')
            if not (final_state.get('genBtn') or {}).get('disabled', True):
                print(f"  Generating video ({gen_text})...")
                page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return;
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate') && !btn.disabled) {
                            btn.click(); return;
                        }
                    }
                }""")

                # Wait for generation (Wan 2.1 takes ~5-10 min)
                print("  Waiting for Wan 2.1 generation (checking every 30s, max 10 min)...")
                for i in range(20):
                    page.wait_for_timeout(30000)
                    elapsed = (i + 1) * 30
                    progress = page.evaluate("""() => {
                        var items = document.querySelectorAll('.result-item');
                        var videoCount = 0;
                        var latestStatus = '';
                        for (var item of items) {
                            var cls = (typeof item.className === 'string') ? item.className : '';
                            if (cls.includes('video')) {
                                videoCount++;
                                if (cls.includes('completed')) latestStatus = 'completed';
                                else if (cls.includes('generating') || cls.includes('progress')) latestStatus = 'generating';
                                else if (cls.includes('queued')) latestStatus = 'queued';
                                else latestStatus = cls.substring(0, 50);
                            }
                        }
                        return {videoCount: videoCount, status: latestStatus};
                    }""")
                    print(f"    [{elapsed}s] videos={progress.get('videoCount', 0)} status={progress.get('status', 'unknown')}")
                    if progress.get('status') == 'completed':
                        break

                screenshot(page, "p241_video_result")
                print("  Video generation done!")
            else:
                print("  Generate button disabled — may need a start frame")
                screenshot(page, "p241_video_disabled")
        else:
            print(f"  Wrong panel, skipping")

    else:
        print(f"  Could not open AI Video panel (got: {panel})")
        # Try opening AI Video directly from sidebar
        if 'AI Video' in sidebar_y:
            print(f"  Trying sidebar at y={sidebar_y['AI Video']}...")
            close_panels(page)
            page.wait_for_timeout(500)
            page.mouse.click(20, sidebar_y['AI Video'])
            page.wait_for_timeout(2500)
            panel = get_active_panel(page)
            print(f"  Panel after sidebar click: {panel}")

    # ================================================================
    # TASK 4: Character Tool
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Character Tool")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    if 'Character' in sidebar_y:
        char_y = sidebar_y['Character']
        print(f"  Character at y={char_y}")
        page.mouse.click(20, char_y)
        page.wait_for_timeout(2500)
    else:
        # Try finding by text click
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Character' && el.offsetHeight > 0 && el.offsetHeight < 50) {
                    var rect = el.getBoundingClientRect();
                    if (rect.x < 60) { el.click(); return; }
                }
            }
        }""")
        page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'character' or panel.startswith('unknown:'):
        char_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            return {
                text: (panel.innerText || '').substring(0, 600),
                buttons: Array.from(panel.querySelectorAll('button')).map(b => (b.innerText || '').trim()).filter(t => t.length > 0 && t.length < 30).slice(0, 20),
                hasUpload: !!panel.querySelector('input[type="file"], [class*="upload"]'),
                hasTa: !!panel.querySelector('textarea')
            };
        }""")
        print(f"  Has upload: {char_map.get('hasUpload')}")
        print(f"  Has textarea: {char_map.get('hasTa')}")
        print(f"  Buttons: {char_map.get('buttons', [])}")
        print(f"  Text:")
        for line in char_map.get('text', '').split('\n')[:20]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")
        screenshot(page, "p241_character")
    else:
        print(f"  Character didn't open (got: {panel})")

    # ================================================================
    # TASK 5: Image Editor
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Image Editor")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    if 'Image Editor' in sidebar_y:
        ie_y = sidebar_y['Image Editor']
        print(f"  Image Editor at y={ie_y}")
        page.mouse.click(20, ie_y)
        page.wait_for_timeout(2500)
    else:
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text === 'Image Editor' || text === 'Image\\nEditor') && el.offsetHeight > 0 && el.offsetHeight < 50) {
                    var rect = el.getBoundingClientRect();
                    if (rect.x < 60) { el.click(); return; }
                }
            }
        }""")
        page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel != 'none':
        ie_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            return {
                text: (panel.innerText || '').substring(0, 500),
                buttons: Array.from(panel.querySelectorAll('button')).map(b => (b.innerText || '').trim()).filter(t => t.length > 0 && t.length < 30).slice(0, 15)
            };
        }""")
        print(f"  Text:")
        for line in ie_map.get('text', '').split('\n')[:15]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")
        print(f"  Buttons: {ie_map.get('buttons', [])}")
        screenshot(page, "p241_image_editor")
    else:
        # Image Editor might not open as a panel — may redirect or be a different UI
        print("  Image Editor didn't open as gen-config panel")
        # Check if it changed the URL or opened a new view
        url = page.url
        print(f"  Current URL: {url}")

        # Check if any new overlay/dialog appeared
        overlay = page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="editor"], [class*="image-edit"]')) {
                if (el.offsetHeight > 100) {
                    return {cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '', text: (el.innerText || '').substring(0, 100)};
                }
            }
            return null;
        }""")
        print(f"  Editor overlay: {json.dumps(overlay)}")
        screenshot(page, "p241_image_editor_state")

    # ================================================================
    # TASK 6: Expression Edit from toolbar
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 6: Expression Edit (toolbar)")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # First click on canvas to select an image element
    page.mouse.click(400, 300)
    page.wait_for_timeout(500)

    # Check top toolbar for Expression button
    expr_btn = page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, [role="button"]')) {
            var text = (el.innerText || el.getAttribute('title') || '').trim();
            if (text === 'Expression' && el.offsetHeight > 0) {
                var rect = el.getBoundingClientRect();
                return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), visible: true};
            }
        }
        return null;
    }""")
    print(f"  Expression button: {json.dumps(expr_btn)}")

    if expr_btn and expr_btn.get('visible'):
        page.mouse.click(expr_btn['x'], expr_btn['y'])
        page.wait_for_timeout(2000)

        # Check what opened
        expr_state = page.evaluate("""() => {
            // Check for Expression popup/overlay
            for (var el of document.querySelectorAll('[class*="expression"], [class*="popup"]')) {
                if (el.offsetHeight > 50) {
                    return {cls: (typeof el.className === 'string') ? el.className.substring(0, 50) : '', text: (el.innerText || '').substring(0, 200)};
                }
            }
            // Check gen-config panel
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) return {panel: (panel.innerText || '').substring(0, 100)};
            return null;
        }""")
        print(f"  Expression state: {json.dumps(expr_state)}")
        screenshot(page, "p241_expression")

    # ================================================================
    # Final Credits
    # ================================================================
    print("\n" + "=" * 70)
    print("Final Credits")
    print("=" * 70)

    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 24 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
