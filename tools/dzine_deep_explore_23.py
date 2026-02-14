#!/usr/bin/env python3
"""Dzine Deep Exploration Part 23 — Chat Editor + HQ Mode + Image Download + Character.

Part 22 findings:
- Img2Img: canvas-based, No Style v2 default, Structure/Color/Face Match, 4 credits Normal
- Img2Img generates 4 variations with numbered action buttons
- 4K NBP confirmed: 5440x3060 at 40 credits
- Sidebar fully visible in screenshot (12 tools)
- Download via expect_download() times out

Part 23 goals:
1. Chat Editor — switch models, test generation with different models
2. Img2Img HQ mode — check cost, generate
3. Image download — try URL extraction from results instead of expect_download
4. Character tool — map panel
5. Instant Storyboard — map panel
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
    """Return active panel type."""
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
        return 'unknown:' + text.substring(0, 50);
    }""")


def close_panels(page):
    """Close open panels and dialogs."""
    page.evaluate("""() => {
        // Close gen-config panel
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
        // Close popups
        for (var el of document.querySelectorAll('.ico-close, [class*="close-btn"]')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 23")
    print("Chat Editor + HQ Mode + Download + Character + Storyboard")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: Download result images via URL extraction
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Download Result Images (URL extraction)")
    print("=" * 70)

    # Switch to Results
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Extract all image URLs from results
    result_images = page.evaluate("""() => {
        var results = [];
        var items = document.querySelectorAll('.result-item');
        for (var i = 0; i < Math.min(items.length, 10); i++) {
            var item = items[i];
            var img = item.querySelector('img');
            var cls = (typeof item.className === 'string') ? item.className : '';
            var type = cls.includes('text-to-image') ? 'txt2img' :
                       cls.includes('image-to-video') ? 'img2video' :
                       cls.includes('image-to-image') ? 'img2img' : 'unknown';
            if (img) {
                results.push({
                    index: i,
                    type: type,
                    src: img.src,
                    naturalW: img.naturalWidth,
                    naturalH: img.naturalHeight,
                    completed: cls.includes('completed')
                });
            }
        }
        return results;
    }""")

    print(f"  Found {len(result_images)} result images:")
    for r in result_images:
        src_short = r['src'][:80] + '...' if len(r['src']) > 80 else r['src']
        print(f"    [{r['index']}] {r['type']} {r['naturalW']}x{r['naturalH']} completed={r['completed']}")
        print(f"        src: {src_short}")

    # Download the first txt2img result (should be 4K NBP from Part 21)
    for r in result_images:
        if r['type'] == 'txt2img' and r['naturalW'] > 0:
            print(f"\n  Downloading {r['type']} [{r['index']}] ({r['naturalW']}x{r['naturalH']})...")
            # Check if it's a blob URL or a real URL
            if r['src'].startswith('blob:'):
                print("  Blob URL — need to convert to data URL first")
                data_url = page.evaluate("""(src) => {
                    return new Promise((resolve) => {
                        var img = document.querySelector('img[src="' + src + '"]');
                        if (!img) return resolve(null);
                        var canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth;
                        canvas.height = img.naturalHeight;
                        var ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0);
                        resolve(canvas.toDataURL('image/png'));
                    });
                }""", r['src'])
                if data_url:
                    print(f"  Got data URL ({len(data_url)} chars)")
            elif r['src'].startswith('http'):
                # Direct URL — save using fetch
                print(f"  HTTP URL — downloading directly...")
                save_path = f"/Users/ray/Documents/openclaw/artifacts/dzine/result_{r['index']}_{r['type']}.png"

                # Use page.evaluate to fetch and convert to base64
                b64 = page.evaluate("""(url) => {
                    return fetch(url)
                        .then(r => r.blob())
                        .then(b => new Promise((resolve) => {
                            var reader = new FileReader();
                            reader.onload = () => resolve(reader.result);
                            reader.readAsDataURL(b);
                        }))
                        .catch(e => 'error: ' + e.message);
                }""", r['src'])

                if b64 and not b64.startswith('error:'):
                    # Save to file
                    import base64
                    # Remove data:image/xxx;base64, prefix
                    data = b64.split(',', 1)[1] if ',' in b64 else b64
                    with open(save_path, 'wb') as f:
                        f.write(base64.b64decode(data))
                    file_size = os.path.getsize(save_path)
                    print(f"  Saved: {save_path} ({file_size:,} bytes)")
                else:
                    print(f"  Fetch failed: {b64[:100] if b64 else 'null'}")
            break

    # Also try to get Img2Img results
    for r in result_images:
        if r['type'] == 'img2img' and r['naturalW'] > 0:
            print(f"\n  Downloading {r['type']} [{r['index']}] ({r['naturalW']}x{r['naturalH']})...")
            save_path = f"/Users/ray/Documents/openclaw/artifacts/dzine/result_{r['index']}_{r['type']}.png"
            if r['src'].startswith('http'):
                b64 = page.evaluate("""(url) => {
                    return fetch(url)
                        .then(r => r.blob())
                        .then(b => new Promise((resolve) => {
                            var reader = new FileReader();
                            reader.onload = () => resolve(reader.result);
                            reader.readAsDataURL(b);
                        }))
                        .catch(e => 'error: ' + e.message);
                }""", r['src'])
                if b64 and not b64.startswith('error:'):
                    import base64
                    data = b64.split(',', 1)[1] if ',' in b64 else b64
                    with open(save_path, 'wb') as f:
                        f.write(base64.b64decode(data))
                    file_size = os.path.getsize(save_path)
                    print(f"  Saved: {save_path} ({file_size:,} bytes)")
            break

    # ================================================================
    # TASK 2: Chat Editor — Model Switching + Generation
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Chat Editor — Model Switching + Test")
    print("=" * 70)

    # The Chat Editor is the bottom bar prompt input
    # First, check what's there
    chat_bar = page.evaluate("""() => {
        // Find the bottom chat input area
        var input = document.querySelector('[data-prompt="true"], .chat-input, [class*="chat-prompt"]');
        if (input) {
            var rect = input.getBoundingClientRect();
            return {found: true, type: 'input', x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)};
        }
        // Look for the text area at bottom
        var bottomBar = document.querySelector('.bottom-bar, [class*="bottom-prompt"]');
        if (bottomBar) {
            var rect = bottomBar.getBoundingClientRect();
            return {found: true, type: 'bar', text: (bottomBar.innerText || '').trim().substring(0, 50), x: Math.round(rect.x), y: Math.round(rect.y)};
        }
        // Look for "Describe the desired image" placeholder
        for (var el of document.querySelectorAll('input, textarea, [contenteditable]')) {
            var ph = el.placeholder || el.getAttribute('data-placeholder') || '';
            if (ph.toLowerCase().includes('describe') || ph.toLowerCase().includes('desired')) {
                var rect = el.getBoundingClientRect();
                return {found: true, type: 'placeholder', placeholder: ph, x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width)};
            }
        }
        return {found: false};
    }""")
    print(f"  Chat bar: {json.dumps(chat_bar)}")

    # Click on the model selector button (left of the chat input)
    model_btn = page.evaluate("""() => {
        var btn = document.querySelector('.option-btn');
        if (btn && btn.offsetHeight > 0) {
            var rect = btn.getBoundingClientRect();
            return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: (btn.innerText || '').trim()};
        }
        return null;
    }""")
    print(f"  Model button: {json.dumps(model_btn)}")

    if model_btn:
        page.mouse.click(model_btn['x'], model_btn['y'])
        page.wait_for_timeout(1000)

        # Map models and their details
        models = page.evaluate("""() => {
            var list = document.querySelector('.option-list');
            if (!list) return [];
            var items = [];
            for (var item of list.querySelectorAll('.option-item')) {
                var name = '';
                var nameEl = item.querySelector('.name, .model-name, span');
                if (nameEl) name = (nameEl.textContent || '').trim().split('\\n')[0];
                if (!name) name = (item.textContent || '').trim().split('\\n')[0];

                var cls = (typeof item.className === 'string') ? item.className : '';
                var badge = item.querySelector('[class*="badge"], [class*="tag"]');
                var badgeText = badge ? (badge.textContent || '').trim() : '';

                // Check for credit cost or other info
                var infoEl = item.querySelector('[class*="info"], [class*="credit"], [class*="cost"]');
                var info = infoEl ? (infoEl.textContent || '').trim() : '';

                var rect = item.getBoundingClientRect();
                items.push({
                    name: name.substring(0, 30),
                    selected: cls.includes('selected') || cls.includes('active'),
                    badge: badgeText,
                    info: info,
                    y: Math.round(rect.y)
                });
            }
            return items;
        }""")

        print(f"\n  Chat Editor models ({len(models)}):")
        for m in models:
            sel = " [SELECTED]" if m.get('selected') else ""
            badge = f" ({m['badge']})" if m.get('badge') else ""
            info = f" — {m['info']}" if m.get('info') else ""
            print(f"    {m['name']}{sel}{badge}{info}")

        screenshot(page, "p231_chat_models")

        # Switch to Nano Banana Pro
        print("\n  Switching to Nano Banana Pro...")
        switched = page.evaluate("""() => {
            var list = document.querySelector('.option-list');
            if (!list) return 'no list';
            for (var item of list.querySelectorAll('.option-item')) {
                var text = (item.textContent || '').trim();
                if (text.includes('Nano Banana Pro')) {
                    item.click();
                    return 'clicked';
                }
            }
            return 'not found';
        }""")
        print(f"  Switch result: {switched}")
        page.wait_for_timeout(500)

        # Verify model changed
        current_model = page.evaluate("""() => {
            var btn = document.querySelector('.option-btn');
            return btn ? (btn.innerText || '').trim() : 'unknown';
        }""")
        print(f"  Current model: {current_model}")

        # Type a test prompt in Chat Editor
        chat_input = page.evaluate("""() => {
            // Find the chat input (textarea/input at bottom)
            var inputs = document.querySelectorAll('textarea, input[type="text"], [contenteditable="true"]');
            for (var input of inputs) {
                var rect = input.getBoundingClientRect();
                // Bottom of screen (y > 350)
                if (rect.y > 350 && rect.width > 200 && rect.height > 0) {
                    return {
                        tag: input.tagName.toLowerCase(),
                        x: Math.round(rect.x + rect.width/2),
                        y: Math.round(rect.y + rect.height/2),
                        placeholder: input.placeholder || ''
                    };
                }
            }
            return null;
        }""")
        print(f"  Chat input: {json.dumps(chat_input)}")

        if chat_input:
            page.mouse.click(chat_input['x'], chat_input['y'])
            page.wait_for_timeout(300)

            # Type prompt
            prompt = "Professional product photo of premium wireless headphones, black matte finish, white background, studio lighting"
            page.keyboard.type(prompt, delay=10)
            page.wait_for_timeout(500)

            screenshot(page, "p231_chat_editor_prompt")

            # Find and check the generate/send button
            send_btn = page.evaluate("""() => {
                // Look for send/generate button near the chat input
                var btns = document.querySelectorAll('button, [class*="send"], [class*="submit"]');
                for (var btn of btns) {
                    var rect = btn.getBoundingClientRect();
                    if (rect.y > 350 && rect.height > 0 && rect.height < 60) {
                        var text = (btn.innerText || btn.getAttribute('title') || '').trim();
                        var cls = (typeof btn.className === 'string') ? btn.className : '';
                        if (cls.includes('generate') || cls.includes('send') || text.length < 10) {
                            return {text: text, cls: cls.substring(0, 40), x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                        }
                    }
                }
                // Also try the yellow circular button
                var circle = document.querySelector('.generate-btn, [class*="chat-generate"]');
                if (circle && circle.offsetHeight > 0) {
                    var rect = circle.getBoundingClientRect();
                    return {text: 'circle', cls: (typeof circle.className === 'string') ? circle.className.substring(0, 40) : '', x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                }
                return null;
            }""")
            print(f"  Send button: {json.dumps(send_btn)}")

            if send_btn:
                # Check credit cost
                cost = page.evaluate("""() => {
                    var btns = document.querySelectorAll('button');
                    for (var btn of btns) {
                        var rect = btn.getBoundingClientRect();
                        if (rect.y > 350) {
                            var text = (btn.innerText || '').trim();
                            var match = text.match(/(\\d+)/);
                            if (match && parseInt(match[1]) > 0 && parseInt(match[1]) < 100) {
                                return {text: text, cost: parseInt(match[1])};
                            }
                        }
                    }
                    return null;
                }""")
                print(f"  Cost: {json.dumps(cost)}")

                # Generate with Chat Editor (NBP model)
                page.mouse.click(send_btn['x'], send_btn['y'])
                print("  Chat Editor generate clicked!")
                page.wait_for_timeout(30000)  # Wait 30s for generation

                screenshot(page, "p231_chat_editor_result")

                # Check result
                chat_result = page.evaluate("""() => {
                    var results = document.querySelectorAll('.result-item');
                    if (results.length === 0) return 'no results';
                    var first = results[0];
                    var cls = (typeof first.className === 'string') ? first.className : '';
                    var img = first.querySelector('img');
                    return {
                        type: cls.substring(0, 60),
                        hasSrc: img ? img.src.substring(0, 80) : 'no img',
                        w: img ? img.naturalWidth : 0,
                        h: img ? img.naturalHeight : 0
                    };
                }""")
                print(f"  Latest result: {json.dumps(chat_result)}")
            else:
                print("  Send button not found")
                # Try pressing Enter
                page.keyboard.press('Enter')
                page.wait_for_timeout(30000)
                screenshot(page, "p231_chat_editor_enter")
        else:
            # Close model dropdown
            page.keyboard.press('Escape')
    else:
        print("  Model button not found")

    # ================================================================
    # TASK 3: Img2Img HQ Mode — Cost + Generate
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Img2Img HQ Mode")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Open Img2Img
    page.mouse.click(40, 240)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'img2img':
        # Click HQ button
        hq_result = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'no panel';
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'HQ') {
                    btn.click();
                    return 'clicked HQ';
                }
            }
            return 'HQ not found';
        }""")
        print(f"  HQ mode: {hq_result}")
        page.wait_for_timeout(500)

        # Check what changed (credit cost, new options)
        hq_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            // Check generate button for cost
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Generate')) {
                    return {genText: (btn.innerText || '').trim()};
                }
            }
            return {text: (panel.innerText || '').substring(0, 400)};
        }""")
        print(f"  HQ mode info: {json.dumps(hq_info)}")

        # Check for quality buttons that might appear in HQ
        hq_options = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var buttons = [];
            for (var btn of panel.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                if (t.length > 0 && t.length < 15) {
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    buttons.push({text: t, selected: cls.includes('selected') || cls.includes('active'), cls: cls.substring(0, 30)});
                }
            }
            return {buttons: buttons};
        }""")
        print(f"  HQ buttons:")
        for b in hq_options.get('buttons', []):
            sel = " [SEL]" if b.get('selected') else ""
            print(f"    [{b['text']}{sel}]  cls={b.get('cls', '')[:25]}")

        screenshot(page, "p231_img2img_hq")

        # Map Structure Match slider range
        slider_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var range = panel.querySelector('input[type="range"]');
            if (range) {
                return {min: range.min, max: range.max, value: range.value, step: range.step || 'none'};
            }
            // Maybe it's a custom slider
            var slider = panel.querySelector('[class*="slider"]');
            if (slider) {
                var rect = slider.getBoundingClientRect();
                return {type: 'custom', cls: (typeof slider.className === 'string') ? slider.className.substring(0, 40) : '', x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width)};
            }
            return {noSlider: true};
        }""")
        print(f"  Structure Match slider: {json.dumps(slider_info)}")

        # Map the Advanced section
        adv_clicked = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'no panel';
            var adv = panel.querySelector('.advanced-btn, button.advanced');
            if (adv) { adv.click(); return 'clicked'; }
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Advanced') { btn.click(); return 'clicked text match'; }
            }
            return 'not found';
        }""")
        print(f"  Advanced section: {adv_clicked}")
        page.wait_for_timeout(500)

        adv_content = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var text = (panel.innerText || '');
            // Get the section after "Advanced"
            var idx = text.indexOf('Advanced');
            if (idx >= 0) {
                var after = text.substring(idx, idx + 300);
                return {advancedSection: after};
            }
            return {fullText: text.substring(0, 600)};
        }""")
        print(f"  Advanced content:")
        text = adv_content.get('advancedSection', adv_content.get('fullText', ''))
        for line in text.split('\n')[:15]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")

        screenshot(page, "p231_img2img_hq_advanced")

        # Switch back to Normal mode
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Normal') { btn.click(); return; }
            }
        }""")
        page.wait_for_timeout(300)

    # ================================================================
    # TASK 4: Character Tool
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Character Tool")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Character is below Img2Img in the sidebar
    # From screenshots: Upload, Assets, Txt2Img, Img2Img, Character
    # Try clicking at approximate y position (between Img2Img and AI Video)
    # Img2Img was at y=240, AI Video was further down
    page.mouse.click(20, 155)  # Try Character position
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel after y=155 click: {panel}")

    if panel == 'none' or panel == 'txt2img':
        # Try other positions
        for y in [165, 175, 185, 195]:
            close_panels(page)
            page.wait_for_timeout(300)
            page.mouse.click(20, y)
            page.wait_for_timeout(1500)
            panel = get_active_panel(page)
            print(f"  Panel after y={y}: {panel}")
            if panel == 'character' or panel.startswith('unknown:'):
                break

    if panel != 'none':
        # Map the panel
        panel_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            return {
                text: (panel.innerText || '').substring(0, 600),
                buttons: Array.from(panel.querySelectorAll('button')).map(b => (b.innerText || '').trim()).filter(t => t.length > 0 && t.length < 30),
                inputs: Array.from(panel.querySelectorAll('input, textarea')).map(i => ({type: i.type || 'text', placeholder: i.placeholder || ''}))
            };
        }""")
        print(f"  Panel text:")
        for line in panel_map.get('text', '').split('\n')[:20]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")
        print(f"  Buttons: {panel_map.get('buttons', [])}")
        print(f"  Inputs: {json.dumps(panel_map.get('inputs', []))}")
        screenshot(page, "p231_character_panel")

    # ================================================================
    # TASK 5: Instant Storyboard (bottom of sidebar)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Instant Storyboard")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Instant Storyboard is at the very bottom of the sidebar
    # Try clicking at various y positions near the bottom
    for y in [370, 380, 390]:
        page.mouse.click(20, y)
        page.wait_for_timeout(1500)
        panel = get_active_panel(page)
        if panel != 'none':
            print(f"  Panel at y={y}: {panel}")
            break
    else:
        # Maybe it opens a different UI (not a gen-config panel)
        print("  No panel opened. Checking for overlay/dialog...")
        overlay = page.evaluate("""() => {
            var overlays = document.querySelectorAll('[class*="storyboard"], [class*="instant"]');
            for (var o of overlays) {
                if (o.offsetHeight > 0) {
                    return {cls: (typeof o.className === 'string') ? o.className.substring(0, 50) : '', text: (o.innerText || '').substring(0, 200)};
                }
            }
            return null;
        }""")
        print(f"  Storyboard overlay: {json.dumps(overlay)}")

    # Try clicking the actual sidebar text
    storyboard_clicked = page.evaluate("""() => {
        // Find by text in sidebar
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Instant Storyboard' || text === 'Instant\\nStoryboard') {
                if (el.offsetHeight > 0 && el.offsetHeight < 60) {
                    var rect = el.getBoundingClientRect();
                    if (rect.x < 80) {
                        el.click();
                        return {clicked: true, y: Math.round(rect.y + rect.height/2)};
                    }
                }
            }
        }
        return {clicked: false};
    }""")
    print(f"  Storyboard click: {json.dumps(storyboard_clicked)}")

    if storyboard_clicked.get('clicked'):
        page.wait_for_timeout(2000)
        panel = get_active_panel(page)
        print(f"  Panel after storyboard click: {panel}")

        # Check for any new UI
        state = page.evaluate("""() => {
            // Check for storyboard-specific UI
            var sb = document.querySelector('[class*="storyboard"]');
            if (sb && sb.offsetHeight > 0) {
                return {found: true, cls: (typeof sb.className === 'string') ? sb.className.substring(0, 50) : '', text: (sb.innerText || '').substring(0, 300)};
            }
            // Check gen-config
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) {
                return {found: true, type: 'gen-config', text: (panel.innerText || '').substring(0, 300)};
            }
            return {found: false};
        }""")
        print(f"  Storyboard state: text={state.get('text', '')[:100]}")
        screenshot(page, "p231_storyboard")

    # ================================================================
    # TASK 6: Image Editor (from sidebar)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 6: Image Editor")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Image Editor is second-to-last in sidebar
    img_editor = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Image Editor' || text === 'Image\\nEditor') {
                if (el.offsetHeight > 0 && el.offsetHeight < 60) {
                    var rect = el.getBoundingClientRect();
                    if (rect.x < 80) {
                        el.click();
                        return {clicked: true, y: Math.round(rect.y + rect.height/2)};
                    }
                }
            }
        }
        return {clicked: false};
    }""")
    print(f"  Image Editor click: {json.dumps(img_editor)}")

    if img_editor.get('clicked'):
        page.wait_for_timeout(2000)
        panel = get_active_panel(page)
        print(f"  Panel: {panel}")

        if panel != 'none':
            ie_map = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                return {
                    text: (panel.innerText || '').substring(0, 400),
                    buttons: Array.from(panel.querySelectorAll('button')).map(b => (b.innerText || '').trim()).filter(t => t.length > 0 && t.length < 30).slice(0, 15)
                };
            }""")
            print(f"  Panel text:")
            for line in ie_map.get('text', '').split('\n')[:15]:
                line = line.strip()
                if line:
                    print(f"    > {line[:60]}")
            print(f"  Buttons: {ie_map.get('buttons', [])}")
            screenshot(page, "p231_image_editor")

    # ================================================================
    # Credits
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
    print("EXPLORATION PART 23 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
