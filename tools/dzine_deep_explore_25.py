#!/usr/bin/env python3
"""Dzine Deep Exploration Part 25 — Model Selector Fix + Video Download + Deep Dives.

Part 24 findings:
- Complete sidebar: Upload(81), Assets(136), Txt2Img(197), Img2Img(252),
  Character(306), AI Video(361), Lip Sync(427), Video Editor(490),
  Motion Control(563), Enhance&Upscale(630), Image Editor(698), Storyboard(778)
- ALL at x=40
- Character: Build/Manage/Generate/Insert/Sheet/360° Video, presets incl 'Ray'
- Image Editor: AI Editor (Local Edit, Insert Object, AI Eraser, Hand Repair, Expand)
               + Face Kit (Face Swap, Face Repair, Expression Edit)
- Model selector: el.click() doesn't work — need page.mouse.click()
- Video generating with Hailuo 2.3 (56 credits, should've been Wan 2.1)

Part 25 goals:
1. Download the generated video
2. Fix model selector — use mouse.click() approach
3. Test Wan 2.1 at 6 credits
4. Test Image Editor → Local Edit workflow
5. Explore Structure Match slider positions for Img2Img fidelity
6. Test Enhance & Upscale on 4K image
"""

import json
import os
import sys
import base64
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
        if (text.startsWith('Image Editor')) return 'image_editor';
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
    print("DZINE DEEP EXPLORATION PART 25")
    print("Model Fix + Video Download + Local Edit + Enhance")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: Download Latest Video Result
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Download Video Result")
    print("=" * 70)

    # Switch to Results
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Find video results and their URLs
    video_results = page.evaluate("""() => {
        var results = [];
        var items = document.querySelectorAll('.result-item');
        for (var i = 0; i < items.length; i++) {
            var cls = (typeof items[i].className === 'string') ? items[i].className : '';
            if (cls.includes('video') || cls.includes('i2v')) {
                var video = items[i].querySelector('video');
                var img = items[i].querySelector('img');
                results.push({
                    index: i,
                    cls: cls.substring(0, 60),
                    completed: cls.includes('completed'),
                    videoSrc: video ? video.src : null,
                    posterSrc: video ? (video.poster || '') : null,
                    imgSrc: img ? img.src : null
                });
            }
        }
        return results;
    }""")

    print(f"  Video results ({len(video_results)}):")
    for v in video_results:
        status = "DONE" if v['completed'] else "pending"
        src = v.get('videoSrc') or v.get('imgSrc') or 'no src'
        print(f"    [{v['index']}] {status} cls={v['cls'][:40]}")
        print(f"        src: {src[:80]}...")

    # Download completed videos
    for v in video_results:
        if v['completed'] and v.get('videoSrc') and v['videoSrc'].startswith('http'):
            print(f"\n  Downloading video [{v['index']}]...")
            save_path = f"/Users/ray/Documents/openclaw/artifacts/dzine/video_{v['index']}.mp4"

            b64 = page.evaluate("""(url) => {
                return fetch(url)
                    .then(r => r.blob())
                    .then(b => new Promise((resolve) => {
                        var reader = new FileReader();
                        reader.onload = () => resolve(reader.result);
                        reader.readAsDataURL(b);
                    }))
                    .catch(e => 'error: ' + e.message);
            }""", v['videoSrc'])

            if b64 and not str(b64).startswith('error:'):
                data = b64.split(',', 1)[1] if ',' in b64 else b64
                with open(save_path, 'wb') as f:
                    f.write(base64.b64decode(data))
                file_size = os.path.getsize(save_path)
                print(f"  Saved: {save_path} ({file_size:,} bytes)")
            else:
                print(f"  Download failed: {str(b64)[:100]}")
            break
        elif v['completed'] and v.get('imgSrc') and 'mp4' in (v.get('imgSrc') or ''):
            # Video might be referenced via image element but is actually mp4
            print(f"\n  Video has img element with mp4 URL...")
            save_path = f"/Users/ray/Documents/openclaw/artifacts/dzine/video_{v['index']}.mp4"
            b64 = page.evaluate("""(url) => {
                return fetch(url).then(r => r.blob()).then(b => new Promise((resolve) => {
                    var reader = new FileReader();
                    reader.onload = () => resolve(reader.result);
                    reader.readAsDataURL(b);
                })).catch(e => 'error: ' + e.message);
            }""", v['imgSrc'])
            if b64 and not str(b64).startswith('error:'):
                data = b64.split(',', 1)[1] if ',' in b64 else b64
                with open(save_path, 'wb') as f:
                    f.write(base64.b64decode(data))
                file_size = os.path.getsize(save_path)
                print(f"  Saved: {save_path} ({file_size:,} bytes)")
            break

    # Also try to find video URL from the DOM more broadly
    all_video_urls = page.evaluate("""() => {
        var urls = [];
        // Check video elements
        for (var v of document.querySelectorAll('video')) {
            if (v.src) urls.push({type: 'video.src', url: v.src});
            for (var s of v.querySelectorAll('source')) {
                if (s.src) urls.push({type: 'source', url: s.src});
            }
        }
        // Check for mp4 URLs in image elements
        for (var img of document.querySelectorAll('img')) {
            if (img.src && img.src.includes('.mp4')) urls.push({type: 'img-mp4', url: img.src});
        }
        return urls;
    }""")
    print(f"\n  All video URLs in DOM ({len(all_video_urls)}):")
    for u in all_video_urls:
        print(f"    {u['type']}: {u['url'][:80]}...")

    # ================================================================
    # TASK 2: Fix AI Video Model Selector
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Fix AI Video Model Selector (use mouse.click)")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Open AI Video from sidebar
    page.mouse.click(40, 361)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'ai_video':
        # Click model selector to open popup
        selector_pos = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var sel = panel.querySelector('.custom-selector-wrapper');
            if (sel) {
                var rect = sel.getBoundingClientRect();
                return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: (sel.innerText || '').trim()};
            }
            return null;
        }""")
        print(f"  Model selector: {json.dumps(selector_pos)}")

        if selector_pos:
            page.mouse.click(selector_pos['x'], selector_pos['y'])
            page.wait_for_timeout(1500)

            # Map the model popup
            popup = page.evaluate("""() => {
                var popup = document.querySelector('.selector-panel, [class*="model-popup"], [class*="selector-popup"]');
                if (!popup) {
                    // Try finding any newly visible overlay
                    for (var el of document.querySelectorAll('[class*="panel"], [class*="popup"]')) {
                        if (el.offsetHeight > 200 && el.offsetWidth > 200) {
                            var text = (el.innerText || '');
                            if (text.includes('Wan 2.1')) {
                                popup = el;
                                break;
                            }
                        }
                    }
                }
                if (!popup) return {found: false};

                // Map all model items with positions
                var items = [];
                for (var el of popup.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Wan 2.1') && el.offsetHeight > 0 && el.offsetHeight < 60) {
                        var rect = el.getBoundingClientRect();
                        items.push({
                            text: text.substring(0, 40),
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            tag: el.tagName.toLowerCase(),
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : ''
                        });
                    }
                }
                // Also get first few models for context
                var allModels = [];
                for (var el of popup.querySelectorAll('[class*="item"], [class*="row"]')) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 3 && text.length < 60 && el.offsetHeight > 20 && el.offsetHeight < 80) {
                        var rect = el.getBoundingClientRect();
                        allModels.push({text: text.split('\\n')[0], y: Math.round(rect.y)});
                    }
                }
                return {found: true, wanItems: items, allModels: allModels.slice(0, 10)};
            }""")

            print(f"  Popup found: {popup.get('found')}")
            if popup.get('wanItems'):
                print(f"  Wan 2.1 elements ({len(popup['wanItems'])}):")
                for w in popup['wanItems']:
                    print(f"    ({w['x']}, {w['y']}) {w['w']}x{w['h']} {w['tag']} cls={w['cls'][:25]} text='{w['text'][:30]}'")

            if popup.get('allModels'):
                print(f"  Visible models:")
                for m in popup['allModels']:
                    print(f"    y={m['y']}: {m['text'][:40]}")

            screenshot(page, "p251_model_popup")

            # Now click Wan 2.1 using mouse.click
            wan_items = popup.get('wanItems', [])
            if wan_items:
                # Pick the most specific element (smallest)
                target = min(wan_items, key=lambda w: w['w'] * w['h'])
                print(f"\n  Clicking Wan 2.1 at ({target['x']}, {target['y']})...")
                page.mouse.click(target['x'], target['y'])
                page.wait_for_timeout(1000)

                # Verify model changed
                new_model = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return 'no panel';
                    var sel = panel.querySelector('.custom-selector-wrapper');
                    return sel ? (sel.innerText || '').trim() : 'unknown';
                }""")
                print(f"  New model: {new_model}")

                if 'Wan 2.1' in new_model:
                    print("  SUCCESS! Wan 2.1 selected!")

                    # Check credit cost
                    cost = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return '';
                        for (var btn of panel.querySelectorAll('button')) {
                            if ((btn.innerText || '').includes('Generate')) {
                                return (btn.innerText || '').trim();
                            }
                        }
                        return '';
                    }""")
                    print(f"  Generate button: {cost}")
                else:
                    print(f"  Still on: {new_model}")
                    # Try scrolling popup to find Wan 2.1
                    print("  Trying scroll + click...")
                    # Wan 2.1 is cheapest = should be near top, but popup might need scroll
                    page.mouse.click(selector_pos['x'], selector_pos['y'])
                    page.wait_for_timeout(1000)

                    # Scroll up in popup
                    page.evaluate("""() => {
                        var popup = document.querySelector('.selector-panel, .panel-body');
                        if (popup) popup.scrollTop = 0;
                    }""")
                    page.wait_for_timeout(500)

                    screenshot(page, "p251_model_popup_scrolled")
            else:
                print("  Wan 2.1 not found in popup — may need scrolling")
                # Try scrolling the popup
                page.evaluate("""() => {
                    var panels = document.querySelectorAll('[class*="panel-body"], [class*="scroll"]');
                    for (var p of panels) {
                        if (p.scrollHeight > p.clientHeight + 50 && p.offsetHeight > 200) {
                            p.scrollTop = 0;
                        }
                    }
                }""")
                page.wait_for_timeout(500)
                screenshot(page, "p251_model_popup_top")

            # Close popup
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)

    # ================================================================
    # TASK 3: Test Enhance & Upscale on 4K Image
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Enhance & Upscale on 4K Result")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Switch to Results, find txt2img section, hover on first result
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Find and click Enhance & Upscale [1] button on the 4K txt2img result
    enhance_clicked = page.evaluate("""() => {
        // Scroll to Txt2Img results section
        var resultContainer = document.querySelector('[class*="result-container"]');
        if (resultContainer) {
            // Scroll down to find txt2img results
            resultContainer.scrollTop = resultContainer.scrollHeight;
        }

        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.startsWith('Enhance')) {
                var rect = c.getBoundingClientRect();
                // Check visibility
                if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                    var btns = c.querySelectorAll('.btn');
                    if (btns.length > 0) {
                        btns[0].click();
                        return {clicked: true, y: Math.round(rect.y)};
                    }
                }
            }
        }
        return {clicked: false};
    }""")
    print(f"  Enhance clicked: {json.dumps(enhance_clicked)}")

    if enhance_clicked.get('clicked'):
        page.wait_for_timeout(2000)

        # Map the Enhance popup
        enhance_popup = page.evaluate("""() => {
            // Look for enhance dialog
            for (var el of document.querySelectorAll('[class*="enhance"], [class*="upscale"], [class*="dialog"], [class*="popup"]')) {
                if (el.offsetHeight > 100 && el.offsetWidth > 200) {
                    var text = (el.innerText || '');
                    if (text.includes('Upscale') || text.includes('Enhance')) {
                        return {
                            found: true,
                            text: text.substring(0, 500),
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : ''
                        };
                    }
                }
            }
            return {found: false};
        }""")

        if enhance_popup.get('found'):
            print(f"  Enhance popup open!")
            print(f"  Text:")
            for line in enhance_popup.get('text', '').split('\n')[:15]:
                line = line.strip()
                if line:
                    print(f"    > {line[:60]}")

            screenshot(page, "p251_enhance_popup")

            # Select 2x upscale (for 4K input = 8K output!)
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('button, [role="button"]')) {
                    if ((el.innerText || '').trim() === '2x') { el.click(); return; }
                }
            }""")
            page.wait_for_timeout(500)

            # Check target resolution
            target_res = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/\\d+\\s*[×x]\\s*\\d+/) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                        return text;
                    }
                }
                return 'unknown';
            }""")
            print(f"  Target resolution at 2x: {target_res}")

            # Check cost
            cost = page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Upscale')) {
                        return (btn.innerText || '').trim();
                    }
                }
                return '';
            }""")
            print(f"  Upscale button: {cost}")

            screenshot(page, "p251_enhance_2x")

            # DON'T click upscale yet — 4K to 8K would be massive
            # Just document the capability
            print("  [NOT CLICKING — documenting capability only]")

            # Close popup
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)
        else:
            print("  Enhance popup not found")
    else:
        print("  Could not find Enhance button in results")

    # ================================================================
    # TASK 4: Image Editor → Local Edit
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Image Editor → Local Edit")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Open Image Editor
    page.mouse.click(40, 698)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'image_editor' or panel.startswith('unknown:Image Editor'):
        # Click Local Edit
        local_edit = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {found: false};
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Local Edit') {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 0) {
                        return {found: true, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                    }
                }
            }
            return {found: false};
        }""")
        print(f"  Local Edit: {json.dumps(local_edit)}")

        if local_edit.get('found'):
            page.mouse.click(local_edit['x'], local_edit['y'])
            page.wait_for_timeout(2000)

            # Check what opened
            le_state = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (panel) return {type: 'panel', text: (panel.innerText || '').substring(0, 400)};
                // Check for new overlay
                for (var el of document.querySelectorAll('[class*="local-edit"], [class*="inpaint"]')) {
                    if (el.offsetHeight > 50) return {type: 'overlay', cls: (typeof el.className === 'string') ? el.className.substring(0, 50) : ''};
                }
                return {type: 'unknown'};
            }""")
            print(f"  Local Edit state: type={le_state.get('type', 'unknown')}")
            if le_state.get('text'):
                for line in le_state['text'].split('\n')[:15]:
                    line = line.strip()
                    if line:
                        print(f"    > {line[:60]}")

            screenshot(page, "p251_local_edit")

    # ================================================================
    # TASK 5: Explore Structure Match for Img2Img fidelity
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Img2Img Structure Match Slider Analysis")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Open Img2Img
    page.mouse.click(40, 252)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'img2img':
        # Map the Structure Match slider in detail
        slider = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var slider = panel.querySelector('.c-slider, [class*="slider"]');
            if (!slider) return {found: false};

            var rect = slider.getBoundingClientRect();

            // Get the value indicator
            var value = panel.querySelector('[class*="slider-value"], [class*="value"]');
            var valueText = '';
            // Check for text near the slider that shows the current value
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t.match(/^0\\.\\d+$/) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                    valueText = t;
                    break;
                }
            }

            // Get the label text
            var labelText = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (['Very similar', 'Similar', 'Less similar', 'Different'].includes(t)) {
                    labelText = t;
                    break;
                }
            }

            // Get tick marks / stops
            var stops = [];
            for (var el of slider.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.width > 2 && r.width < 10 && r.height > 2 && r.height < 15) {
                    stops.push(Math.round(r.x));
                }
            }

            return {
                found: true,
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
                value: valueText,
                label: labelText,
                stops: stops.length
            };
        }""")
        print(f"  Slider: {json.dumps(slider)}")

        if slider.get('found'):
            # Test different slider positions
            sx = slider['x']
            sy = slider['y'] + slider['h'] // 2
            sw = slider['w']

            # Positions to test: 0%, 25%, 50%, 75%, 100%
            for pct in [0, 25, 50, 75, 100]:
                click_x = sx + int(sw * pct / 100)
                page.mouse.click(click_x, sy)
                page.wait_for_timeout(500)

                # Read current value and label
                current = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var value = '';
                    for (var el of panel.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (t.match(/^0\\.\\d+$/) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                            value = t; break;
                        }
                    }
                    var label = '';
                    for (var el of panel.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact'].includes(t)) {
                            label = t; break;
                        }
                    }
                    return {value: value, label: label};
                }""")
                print(f"    {pct}%: value={current.get('value', '?')} label='{current.get('label', '?')}'")

            # Set back to max (100%) for best fidelity
            page.mouse.click(sx + sw, sy)
            page.wait_for_timeout(300)

    # ================================================================
    # TASK 6: Map Editing Toolbar (appears when image selected)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 6: Map Editing Toolbar (with canvas selection)")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Click on the canvas image to select it
    page.mouse.click(400, 300)
    page.wait_for_timeout(1000)

    # Now check the toolbar
    toolbar = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('button, [role="button"]')) {
            var rect = el.getBoundingClientRect();
            // Toolbar area (y between 30-60, x > 100)
            if (rect.y > 25 && rect.y < 65 && rect.x > 100 && rect.height > 15 && rect.height < 45) {
                var text = (el.innerText || el.getAttribute('title') || '').trim();
                if (text.length > 0 && text.length < 25) {
                    items.push({
                        text: text,
                        x: Math.round(rect.x + rect.width / 2),
                        y: Math.round(rect.y + rect.height / 2)
                    });
                }
            }
        }
        // Deduplicate
        var seen = {};
        return items.filter(i => {
            if (seen[i.text]) return false;
            seen[i.text] = true;
            return true;
        }).sort((a, b) => a.x - b.x);
    }""")

    print(f"  Toolbar buttons ({len(toolbar)}):")
    for t in toolbar:
        print(f"    x={t['x']:4d}  y={t['y']:2d}  '{t['text']}'")

    screenshot(page, "p251_toolbar_selected")

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
    print("EXPLORATION PART 25 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
