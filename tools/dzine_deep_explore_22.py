#!/usr/bin/env python3
"""Dzine Deep Exploration Part 22 — Img2Img Full Workflow + Result Check.

Part 21 findings:
- Pick Image dialog closed OK
- Txt2Img at y=190 works, NBP at 4K = 5440x3060, costs 40 credits
- Img2Img at y=240 DOES open — panel text is "Image-to-Image" (hyphenated)
- Sidebar icon mapping failed (elements not in x<80 strip or use flex layout)

Part 22 goals:
1. Check if 4K generation from Part 21 produced a result
2. Fully map the Img2Img panel (model, controls, sliders, upload)
3. Upload a product image and generate a variation
4. Map sidebar icons using a different approach (hover tooltips or aria-labels)
5. Test image download from results
"""

import json
import os
import sys
import time
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def get_active_panel(page):
    """Return which panel/tool is currently active. FIXED: handles Image-to-Image."""
    return page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        var text = (panel.innerText || '').substring(0, 100).trim();
        if (text.startsWith('Text to Image') || text.startsWith('Text-to-Image')) return 'txt2img';
        if (text.startsWith('AI Video')) return 'ai_video';
        if (text.startsWith('Enhance & Upscale')) return 'enhance';
        if (text.startsWith('Motion Control')) return 'motion';
        if (text.startsWith('Face Swap')) return 'face_swap';
        if (text.startsWith('Image-to-Image') || text.startsWith('Image to Image') || text.startsWith('Img2Img')) return 'img2img';
        return 'unknown:' + text.substring(0, 50);
    }""")


def close_panels(page):
    """Close open panels."""
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 22")
    print("Img2Img Full Workflow + Result Check + Sidebar Map")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # STEP 1: Check Part 21 generation result
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 1: Check 4K NBP Generation Result from Part 21")
    print("=" * 70)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Get latest results
    results = page.evaluate("""() => {
        var items = document.querySelectorAll('.result-item, [class*="result-item"]');
        var results = [];
        for (var i = 0; i < Math.min(items.length, 5); i++) {
            var item = items[i];
            var img = item.querySelector('img');
            var cls = (typeof item.className === 'string') ? item.className : '';
            var rect = item.getBoundingClientRect();
            results.push({
                index: i,
                cls: cls.substring(0, 80),
                hasSrc: img ? img.src.substring(0, 80) : 'no img',
                visible: rect.height > 0,
                y: Math.round(rect.y)
            });
        }
        return {total: items.length, items: results};
    }""")
    print(f"  Total results: {results.get('total', 0)}")
    for r in results.get('items', []):
        print(f"    [{r['index']}] y={r['y']} visible={r['visible']} cls={r['cls'][:40]}")

    # Check if the latest result has 4K dimensions
    latest = page.evaluate("""() => {
        var items = document.querySelectorAll('.result-item');
        if (items.length === 0) return {};
        var first = items[0];
        var img = first.querySelector('img');
        var info = first.querySelector('[class*="info"], [class*="detail"]');
        return {
            imgSrc: img ? img.src.substring(0, 100) : 'no img',
            infoText: info ? (info.innerText || '').trim().substring(0, 100) : '',
            cls: (typeof first.className === 'string') ? first.className : '',
            naturalW: img ? img.naturalWidth : 0,
            naturalH: img ? img.naturalHeight : 0
        };
    }""")
    print(f"  Latest result: w={latest.get('naturalW', 0)} h={latest.get('naturalH', 0)}")
    print(f"  Class: {latest.get('cls', '')[:60]}")

    screenshot(page, "p221_results_check")

    # ================================================================
    # STEP 2: Map sidebar icons using scroll and DOM inspection
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 2: Map Sidebar Icons")
    print("=" * 70)

    # The sidebar icons are likely in a flex/grid container
    sidebar_info = page.evaluate("""() => {
        // Try multiple selectors for the sidebar
        var selectors = [
            '.c-side-tools',
            '[class*="side-bar"]',
            '[class*="sidebar"]',
            '[class*="tool-bar"]',
            '[class*="left-bar"]'
        ];
        for (var sel of selectors) {
            var el = document.querySelector(sel);
            if (el && el.offsetHeight > 0) {
                var rect = el.getBoundingClientRect();
                // Get all child elements that look like buttons/icons
                var children = [];
                for (var child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    if (cr.width > 15 && cr.height > 15 && cr.width < 80 && cr.height < 80
                        && cr.x < 100 && cr.y > 50) {
                        var text = (child.getAttribute('title') || child.getAttribute('aria-label') ||
                                   child.getAttribute('data-tooltip') || child.getAttribute('data-tip') ||
                                   (child.innerText || '').trim());
                        if (text.length < 30 && text.length > 0) {
                            children.push({
                                text: text,
                                x: Math.round(cr.x + cr.width/2),
                                y: Math.round(cr.y + cr.height/2),
                                tag: child.tagName.toLowerCase(),
                                cls: (typeof child.className === 'string') ? child.className.substring(0, 40) : ''
                            });
                        }
                    }
                }
                return {
                    selector: sel,
                    rect: {x: rect.x, y: rect.y, w: rect.width, h: rect.height},
                    childCount: children.length,
                    children: children.slice(0, 30)
                };
            }
        }

        // Fallback: check all elements in left 80px that have click handlers or are buttons
        var leftElements = [];
        for (var el of document.querySelectorAll('button, [role="button"], a, [tabindex], svg, img')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 0 && r.x < 80 && r.y > 50 && r.y < 700 && r.height > 10 && r.width > 10) {
                var text = (el.getAttribute('title') || el.getAttribute('aria-label') || '').trim();
                if (!text) text = (el.innerText || '').trim().substring(0, 20);
                leftElements.push({
                    text: text,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    tag: el.tagName.toLowerCase(),
                    cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : ''
                });
            }
        }
        return {selector: 'fallback-left80', childCount: leftElements.length, children: leftElements};
    }""")

    print(f"  Found via: {sidebar_info.get('selector', 'unknown')}")
    if 'rect' in sidebar_info:
        r = sidebar_info['rect']
        print(f"  Sidebar bounds: x={r['x']} y={r['y']} w={r['w']} h={r['h']}")
    print(f"  Child elements: {sidebar_info.get('childCount', 0)}")

    children = sidebar_info.get('children', [])
    # Deduplicate by y-position
    seen_y = set()
    unique_children = []
    for c in sorted(children, key=lambda x: x['y']):
        y_key = round(c['y'] / 15) * 15
        if y_key not in seen_y:
            seen_y.add(y_key)
            unique_children.append(c)

    for c in unique_children:
        print(f"    y={c['y']:3d} x={c['x']:2d}  {c['tag']:5s}  text='{c.get('text', '')[:25]}'  cls={c.get('cls', '')[:25]}")

    # ================================================================
    # STEP 3: Img2Img — Full Panel Mapping
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 3: Img2Img — Full Panel Mapping")
    print("=" * 70)

    # Close any open panel
    close_panels(page)
    page.wait_for_timeout(500)

    # Click Img2Img sidebar (y=240)
    page.mouse.click(40, 240)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'img2img':
        # Full panel mapping
        mapping = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};

            // Model
            var sn = panel.querySelector('.style-name');
            var model = sn ? (sn.innerText || '').trim() : 'unknown';

            // Prompt textarea
            var ta = panel.querySelector('textarea');
            var prompt = ta ? {
                placeholder: (ta.placeholder || ''),
                maxLength: ta.maxLength || 0,
                value: (ta.value || '').substring(0, 50)
            } : null;

            // All buttons
            var buttons = [];
            for (var btn of panel.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                var cls = (typeof btn.className === 'string') ? btn.className : '';
                if (t.length > 0 && t.length < 40) {
                    buttons.push({text: t, cls: cls.substring(0, 40)});
                }
            }

            // All sliders / range inputs
            var sliders = [];
            for (var s of panel.querySelectorAll('input[type="range"]')) {
                sliders.push({
                    min: s.min, max: s.max, value: s.value, step: s.step
                });
            }

            // Sections / labels
            var labels = [];
            for (var el of panel.querySelectorAll('label, .label, [class*="label"], [class*="title"]')) {
                var t = (el.innerText || '').trim();
                if (t.length > 0 && t.length < 40) labels.push(t);
            }

            // Upload area
            var upload = panel.querySelector('[class*="upload"], [class*="drop-zone"], [class*="pick-image"]');
            var uploadInfo = upload ? {
                cls: (typeof upload.className === 'string') ? upload.className.substring(0, 50) : '',
                text: (upload.innerText || '').trim().substring(0, 50)
            } : null;

            // File input
            var fileInput = panel.querySelector('input[type="file"]');

            // Quality options
            var qualityBtns = [];
            for (var btn of panel.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                if (['1K', '2K', '4K'].includes(t)) {
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    qualityBtns.push({text: t, selected: cls.includes('selected') || cls.includes('active')});
                }
            }

            return {
                model: model,
                prompt: prompt,
                buttons: buttons,
                sliders: sliders,
                labels: labels,
                upload: uploadInfo,
                hasFileInput: !!fileInput,
                qualityBtns: qualityBtns,
                fullText: (panel.innerText || '').substring(0, 800)
            };
        }""")

        print(f"  Model: {mapping.get('model')}")
        print(f"  Prompt: {json.dumps(mapping.get('prompt'))}")
        print(f"  Has file input: {mapping.get('hasFileInput')}")
        print(f"  Upload area: {json.dumps(mapping.get('upload'))}")
        print(f"  Quality buttons: {json.dumps(mapping.get('qualityBtns'))}")
        print(f"  Sliders: {json.dumps(mapping.get('sliders'))}")
        print(f"\n  Labels ({len(mapping.get('labels', []))}):")
        for l in mapping.get('labels', []):
            print(f"    > {l}")
        print(f"\n  Buttons ({len(mapping.get('buttons', []))}):")
        for b in mapping.get('buttons', []):
            print(f"    > [{b['text']}]  cls={b['cls'][:30]}")
        print(f"\n  Full text:")
        for line in mapping.get('fullText', '').split('\n')[:30]:
            line = line.strip()
            if line:
                print(f"    > {line[:70]}")

        screenshot(page, "p221_img2img_full_map")

        # ================================================================
        # STEP 4: Configure Img2Img for maximum quality
        # ================================================================
        print("\n" + "=" * 70)
        print("STEP 4: Configure Img2Img — NBP + 4K + Upload Image")
        print("=" * 70)

        # Check if model is NBP, if not switch
        if mapping.get('model') != 'Nano Banana Pro':
            print(f"  Current model: {mapping.get('model')} — switching to NBP...")
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                var btn = panel.querySelector('button.style, .style-btn, [class*="style-select"]');
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(2000)

            # Click NBP in style list
            nbp_result = page.evaluate("""() => {
                var items = document.querySelectorAll('[class*="style-item"], [class*="model-card"]');
                for (var item of items) {
                    if ((item.innerText || '').includes('Nano Banana Pro')) {
                        item.click();
                        return 'clicked';
                    }
                }
                // Try in the style list panel
                var panel = document.querySelector('.style-list-panel');
                if (panel) {
                    for (var el of panel.querySelectorAll('*')) {
                        if ((el.innerText || '').trim() === 'Nano Banana Pro') {
                            // Click the parent card
                            var card = el.closest('[class*="item"], [class*="card"]');
                            if (card) { card.click(); return 'clicked card'; }
                            el.click();
                            return 'clicked text';
                        }
                    }
                }
                return 'not found';
            }""")
            print(f"  NBP selection: {nbp_result}")
            page.wait_for_timeout(1000)
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

        # Select 4K quality
        print("  Selecting 4K quality...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === '4K') { btn.click(); return; }
            }
        }""")
        page.wait_for_timeout(300)

        # Check for reference image upload area
        # Try clicking "Upload Image" or "Pick Image" button if exists
        upload_result = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'no panel';

            // Look for upload buttons
            for (var el of panel.querySelectorAll('button, div[class*="upload"], div[class*="pick"]')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.includes('upload') || text.includes('pick image') || text.includes('add image') ||
                    text.includes('choose') || text.includes('select image')) {
                    if (el.offsetHeight > 0) {
                        var rect = el.getBoundingClientRect();
                        return {found: true, text: (el.innerText || '').trim(), x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                    }
                }
            }

            // Check for drag-and-drop area
            var dropZone = panel.querySelector('[class*="drop"], [class*="upload-area"], [class*="image-input"]');
            if (dropZone && dropZone.offsetHeight > 0) {
                var rect = dropZone.getBoundingClientRect();
                return {found: true, type: 'dropzone', text: (dropZone.innerText || '').trim().substring(0, 50), x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
            }

            // Check for the reference image section
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Reference Image' || text === 'Input Image') {
                    var rect = el.getBoundingClientRect();
                    return {found: true, type: 'label', text: text, y: Math.round(rect.y)};
                }
            }

            return {found: false};
        }""")
        print(f"  Upload area: {json.dumps(upload_result)}")

        # Look for file input specifically
        file_inputs = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var inputs = [];
            for (var input of panel.querySelectorAll('input[type="file"]')) {
                inputs.push({
                    accept: input.accept || '',
                    name: input.name || '',
                    visible: input.offsetHeight > 0,
                    style: input.style.display || ''
                });
            }
            // Also check globally (might be outside panel)
            for (var input of document.querySelectorAll('input[type="file"]')) {
                var rect = input.getBoundingClientRect();
                inputs.push({
                    accept: input.accept || '',
                    name: input.name || '',
                    visible: input.offsetHeight > 0,
                    parentCls: (typeof input.parentElement.className === 'string') ? input.parentElement.className.substring(0, 40) : '',
                    global: true
                });
            }
            return inputs;
        }""")
        print(f"  File inputs: {json.dumps(file_inputs)}")

        # Enter a prompt for Img2Img
        prompt = "Premium wireless noise-cancelling headphones, professional product photography, white studio background, extremely detailed, photorealistic, 8K quality, Amazon product listing"
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

        # Try using the Describe Canvas / auto-prompt feature
        auto_prompt = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'no panel';
            var btn = panel.querySelector('.autoprompt, button.autoprompt, [class*="auto-prompt"]');
            if (btn && btn.offsetHeight > 0) { btn.click(); return 'clicked'; }
            // Also try "Describe" button
            for (var b of panel.querySelectorAll('button')) {
                var t = (b.innerText || '').trim().toLowerCase();
                if (t.includes('describe') || t.includes('auto')) {
                    if (b.offsetHeight > 0) { b.click(); return 'clicked: ' + t; }
                }
            }
            return 'not found';
        }""")
        print(f"  Auto-prompt: {auto_prompt}")
        if auto_prompt.startswith('clicked'):
            page.wait_for_timeout(5000)

        # Check for canvas image usage (Img2Img might use what's on the canvas)
        canvas_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            // Check if there's a preview/thumbnail of the input image
            var preview = panel.querySelector('img[class*="preview"], img[class*="thumb"], img[class*="input"]');
            var previewInfo = preview ? {
                src: preview.src.substring(0, 80),
                w: preview.naturalWidth,
                h: preview.naturalHeight
            } : null;
            // Check if "Use Canvas" is mentioned
            var text = (panel.innerText || '');
            var usesCanvas = text.includes('canvas') || text.includes('Canvas');
            return {preview: previewInfo, usesCanvas: usesCanvas};
        }""")
        print(f"  Canvas state: {json.dumps(canvas_state)}")

        screenshot(page, "p221_img2img_configured")

        # ================================================================
        # STEP 5: Generate Img2Img (if configured correctly)
        # ================================================================
        print("\n" + "=" * 70)
        print("STEP 5: Generate Img2Img")
        print("=" * 70)

        # Safety: verify we're still on Img2Img panel
        safety = get_active_panel(page)
        print(f"  Safety check: {safety}")

        if safety == 'img2img':
            gen_info = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                // Find generate button
                for (var btn of panel.querySelectorAll('button')) {
                    var text = (btn.innerText || '').trim();
                    if (text.includes('Generate')) {
                        return {
                            text: text,
                            disabled: btn.disabled,
                            cls: (typeof btn.className === 'string') ? btn.className.substring(0, 40) : ''
                        };
                    }
                }
                return {notFound: true};
            }""")
            print(f"  Generate button: {json.dumps(gen_info)}")

            if gen_info.get('text') and not gen_info.get('disabled') and not gen_info.get('notFound'):
                # Click Generate
                page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return;
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate') && !btn.disabled) {
                            btn.click(); return;
                        }
                    }
                }""")
                print("  Img2Img Generate clicked! Waiting (90s)...")

                for i in range(6):
                    page.wait_for_timeout(15000)
                    progress = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return 'no panel';
                        // Check for loading/progress indicators
                        var loading = panel.querySelector('[class*="loading"], [class*="progress"], [class*="generating"]');
                        if (loading && loading.offsetHeight > 0) return 'generating...';
                        return 'idle';
                    }""")
                    elapsed = (i + 1) * 15
                    print(f"    [{elapsed}s] {progress}")

                screenshot(page, "p221_img2img_result")
                print("  Img2Img generation done!")
            else:
                print("  Generate button not ready — may need an input image first")
                screenshot(page, "p221_img2img_needs_input")
        else:
            print(f"  Wrong panel: {safety}")

    else:
        # Try opening from a different approach — maybe result actions
        print(f"  Img2Img panel didn't match (got: {panel})")
        print("  Trying to open via result actions...")

        # Click on a result image, then use its Img2Img action
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(500)

        # Hover on first result to get action buttons
        first_result = page.evaluate("""() => {
            var item = document.querySelector('.result-item');
            if (!item) return null;
            var rect = item.getBoundingClientRect();
            return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
        }""")
        if first_result:
            page.mouse.move(first_result['x'], first_result['y'])
            page.wait_for_timeout(1000)

            actions = page.evaluate("""() => {
                var btns = document.querySelectorAll('.btn-container .btn, [class*="action-btn"]');
                var result = [];
                for (var btn of btns) {
                    if (btn.offsetHeight > 0) {
                        var text = (btn.innerText || btn.getAttribute('title') || '').trim();
                        var rect = btn.getBoundingClientRect();
                        result.push({text: text, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                    }
                }
                return result;
            }""")
            print(f"  Result actions ({len(actions)}):")
            for a in actions:
                print(f"    > '{a['text']}' at ({a['x']}, {a['y']})")

    # ================================================================
    # STEP 6: Download a result image
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 6: Download Result Image")
    print("=" * 70)

    # Switch to Results
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Hover on first result
    first = page.evaluate("""() => {
        var item = document.querySelector('.result-item');
        if (!item) return null;
        var rect = item.getBoundingClientRect();
        return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
    }""")

    if first:
        page.mouse.move(first['x'], first['y'])
        page.wait_for_timeout(1000)

        # Look for download button
        download_btn = page.evaluate("""() => {
            var btns = document.querySelectorAll('.btn-container .btn, [class*="action"] button, [class*="download"]');
            for (var btn of btns) {
                var text = (btn.innerText || btn.getAttribute('title') || '').trim().toLowerCase();
                if (text.includes('download') && btn.offsetHeight > 0) {
                    var rect = btn.getBoundingClientRect();
                    return {text: text, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                }
            }
            return null;
        }""")
        print(f"  Download button: {json.dumps(download_btn)}")

        if download_btn:
            # Set up download listener
            with page.expect_download(timeout=30000) as download_info:
                page.mouse.click(download_btn['x'], download_btn['y'])
            download = download_info.value
            save_path = f"/Users/ray/Documents/openclaw/artifacts/dzine/latest_result.png"
            download.save_as(save_path)
            print(f"  Downloaded to: {save_path}")
        else:
            # Try right-clicking the image for download option
            print("  No download button visible. Trying right-click approach...")
            # Map the action buttons that appear on hover
            hover_actions = page.evaluate("""() => {
                var container = document.querySelector('.btn-container');
                if (!container || container.offsetHeight === 0) return [];
                var btns = [];
                for (var btn of container.querySelectorAll('.btn')) {
                    if (btn.offsetHeight > 0) {
                        var text = (btn.innerText || btn.getAttribute('title') || '').trim();
                        var rect = btn.getBoundingClientRect();
                        btns.push({text: text, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                    }
                }
                return btns;
            }""")
            print(f"  Hover actions: {json.dumps(hover_actions)}")

    # ================================================================
    # Final credits
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
    print("EXPLORATION PART 22 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
